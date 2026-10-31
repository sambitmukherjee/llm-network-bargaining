"""Theory benchmarks for LLM exchange-network experiments.

For each network (every link = a 24-point pie, 1-exchange rule) compute:
  - Myerson value (Jackson-Wolinsky sense: Shapley value of w(S) = max-weight matching on g[S])
  - Position value (Meessen 1988; Borm, Owen & Tijs 1992; network-game version): Shapley value of
    the LINK game r(A) = value of the network made of links A, each link's value split equally
    between its two endpoints
  - Core: emptiness check + min/max payoff of each node over the core (LP)
  - Nucleolus (sequential LP; equals a balanced outcome = core ∩ prekernel when the core is non-empty)
  - Balanced outcome via local edge-balancing dynamics (Kleinberg-Tardos), as a cross-check
Also broker (relay) networks: Myerson's original communication-restricted game.

Read the nucleolus column as the balanced outcome; the dynamics are only a cross-check
and can fail to settle on longer lines (e.g. the 7-line), where they print "none".
Usage: pip install networkx scipy numpy && python predict.py   (writes predictions.json)
If you use this during the sprint, mark it as pre-existing code in your README and report.
"""
import itertools, math, json
import networkx as nx
import numpy as np
from scipy.optimize import linprog

PIE = 24.0
TOL = 1e-7


def subsets(nodes):
    for r in range(len(nodes) + 1):
        for S in itertools.combinations(nodes, r):
            yield frozenset(S)


def matching_value(G, S):
    H = G.subgraph(S)
    if H.number_of_edges() == 0:
        return 0.0
    M = nx.max_weight_matching(H, weight="weight")
    return float(sum(H[u][v]["weight"] for u, v in M))


def broker_value(G, S, src="A", dst="C"):
    if src in S and dst in S and nx.has_path(G.subgraph(S), src, dst):
        return PIE
    return 0.0


def build_v(G, valfun):
    nodes = list(G.nodes())
    return {S: valfun(G, S) for S in subsets(nodes)}


def shapley(nodes, v):
    n = len(nodes)
    phi = {i: 0.0 for i in nodes}
    for i in nodes:
        others = [j for j in nodes if j != i]
        for r in range(len(others) + 1):
            w = math.factorial(r) * math.factorial(n - r - 1) / math.factorial(n)
            for S in itertools.combinations(others, r):
                S = frozenset(S)
                phi[i] += w * (v[S | {i}] - v[S])
    return phi


def position_value(G, link_value):
    """Network-game position value: half of each incident link's Shapley value in the link game.

    link_value(G, links) -> value of the network made of `links`. Exact; one player per link,
    so cost grows as 2^(number of links): fine for the small networks here, sample beyond ~20 links.
    """
    links = [tuple(e) for e in G.edges()]
    r = {}
    for k in range(len(links) + 1):
        for A in itertools.combinations(links, k):
            r[frozenset(A)] = link_value(G, A)
    phi_link = shapley(links, r)
    pv = {x: 0.0 for x in G.nodes()}
    for (a, b), val in phi_link.items():
        pv[a] += val / 2
        pv[b] += val / 2
    return pv


def matching_link_value(G, links):
    """24 x maximum matching of the network formed by `links` (exchange networks)."""
    if not links:
        return 0.0
    H = nx.Graph()
    H.add_edges_from((a, b, {"weight": G[a][b]["weight"]}) for a, b in links)
    M = nx.max_weight_matching(H, weight="weight")
    return float(sum(H[u][v]["weight"] for u, v in M))


def broker_link_value(G, links, src="A", dst="C"):
    """24 if src and dst are connected through `links` (Myerson's communication game)."""
    H = nx.Graph()
    H.add_edges_from(links)
    if H.has_node(src) and H.has_node(dst) and nx.has_path(H, src, dst):
        return PIE
    return 0.0


def lp_rows(nodes, coalitions):
    idx = {x: k for k, x in enumerate(nodes)}
    rows = []
    for S in coalitions:
        row = np.zeros(len(nodes))
        for x in S:
            row[idx[x]] = 1.0
        rows.append(row)
    return np.array(rows)


def core_bounds(nodes, v):
    """Return {node: (min, max)} over the core, or None if the core is empty."""
    N = frozenset(nodes)
    proper = [S for S in v if 0 < len(S) < len(nodes)]
    A = lp_rows(nodes, proper)
    b = np.array([v[S] for S in proper])
    A_ub, b_ub = -A, -b  # x(S) >= v(S)
    A_eq, b_eq = np.ones((1, len(nodes))), np.array([v[N]])
    out = {}
    for k, x in enumerate(nodes):
        c = np.zeros(len(nodes)); c[k] = 1.0
        lo = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                     bounds=[(None, None)] * len(nodes), method="highs")
        if lo.status != 0:
            return None
        hi = linprog(-c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                     bounds=[(None, None)] * len(nodes), method="highs")
        out[x] = (round(lo.fun, 4), round(-hi.fun, 4))
    return out


def nucleolus(nodes, v):
    """Sequential-LP nucleolus (Maschler-Peleg-Shapley). Returns {node: payoff}."""
    n = len(nodes)
    N = frozenset(nodes)
    active = [S for S in v if 0 < len(S) < n]
    fixed = []  # (S, excess)
    x_sol = None
    for _ in range(4 * len(active) + 5):
        if not active:
            break
        # variables: x_1..x_n, eps ; maximize eps
        nv = n + 1
        A_ub, b_ub, A_eq, b_eq = [], [], [], []
        rows_active = lp_rows(nodes, active)
        for row, S in zip(rows_active, active):
            # x(S) - v(S) >= eps  ->  -x(S) + eps <= -v(S)
            A_ub.append(np.append(-row, 1.0)); b_ub.append(-v[S])
        for S, e in fixed:
            row = lp_rows(nodes, [S])[0]
            A_eq.append(np.append(row, 0.0)); b_eq.append(v[S] + e)
        A_eq.append(np.append(np.ones(n), 0.0)); b_eq.append(v[N])
        c = np.zeros(nv); c[-1] = -1.0
        res = linprog(c, A_ub=np.array(A_ub), b_ub=np.array(b_ub), A_eq=np.array(A_eq),
                      b_eq=np.array(b_eq), bounds=[(None, None)] * nv, method="highs")
        eps = res.x[-1]
        x_sol = res.x[:n]
        # find coalitions tight in every optimum: max of x(S)-v(S) given eps fixed
        A_ub2 = [np.append(-row, 0.0) for row in rows_active]
        b_ub2 = [-(v[S] + eps) for S in active]
        newly = []
        for row, S in zip(rows_active, active):
            c2 = np.append(-row, 0.0)
            r2 = linprog(c2, A_ub=np.array(A_ub2), b_ub=np.array(b_ub2), A_eq=np.array(A_eq),
                         b_eq=np.array(b_eq), bounds=[(None, None)] * nv, method="highs")
            if r2.status == 0 and (-r2.fun - v[S]) <= eps + 1e-6:
                newly.append(S)
        if not newly:
            break
        for S in newly:
            fixed.append((S, eps))
            active.remove(S)
        # stop if fixed coalitions pin down x uniquely
        M = lp_rows(nodes, [S for S, _ in fixed] + [N])
        if np.linalg.matrix_rank(M) >= n:
            break
    return {x: round(float(val), 4) for x, val in zip(nodes, x_sol)}


def balanced_dynamics(G, iters=20000, lam=0.3):
    """Edge-balancing dynamics on each maximum matching; return first stable fixed point."""
    best_w = matching_value(G, frozenset(G.nodes()))
    edges = list(G.edges())
    candidates = []
    for r in range(1, len(G.nodes()) // 2 + 1):
        for M in itertools.combinations(edges, r):
            used = [x for e in M for x in e]
            if len(used) != len(set(used)):
                continue
            if abs(sum(G[a][b]["weight"] for a, b in M) - best_w) < TOL:
                candidates.append(M)
    for M in candidates:
        partner = {}
        for a, b in M:
            partner[a] = b; partner[b] = a
        u = {x: 0.0 for x in G.nodes()}
        for a, b in M:
            u[a] = u[b] = G[a][b]["weight"] / 2
        for _ in range(iters):
            alpha = {}
            for i in G.nodes():
                best = 0.0
                for k in G.neighbors(i):
                    if partner.get(i) == k:
                        continue
                    best = max(best, G[i][k]["weight"] - u[k])
                alpha[i] = best
            new = dict(u)
            for a, b in M:
                w = G[a][b]["weight"]
                s = w - alpha[a] - alpha[b]
                if s >= -TOL:
                    new[a] = alpha[a] + s / 2
                    new[b] = alpha[b] + s / 2
            for x in G.nodes():
                if x not in partner:
                    new[x] = 0.0
            u = {x: (1 - lam) * u[x] + lam * new[x] for x in G.nodes()}
        stable = all(u[i] + u[j] >= G[i][j]["weight"] - 1e-4 for i, j in G.edges())
        if stable:
            return {x: round(val, 3) for x, val in u.items()}, M
    return None, None


def make(edges):
    G = nx.Graph()
    for a, b in edges:
        G.add_edge(a, b, weight=PIE)
    return G


def path(n):
    names = "ABCDEFGH"[:n]
    return make([(names[i], names[i + 1]) for i in range(n - 1)])


def star(k):
    return make([("H", f"L{i+1}") for i in range(k)])


exchange_networks = {
    "dyad": path(2),
    "path3": path(3),
    "path4": path(4),
    "path5": path(5),
    "path6": path(6),
    "path7": path(7),
    "star3": star(3),
    "star4": star(4),
    "star5": star(5),
    "stem": make([("A", "B"), ("B", "C"), ("B", "D"), ("C", "D")]),
    "triangle": make([("A", "B"), ("B", "C"), ("C", "A")]),
}

results = {}
for name, G in exchange_networks.items():
    nodes = list(G.nodes())
    v = build_v(G, matching_value)
    phi = shapley(nodes, v)
    pos = position_value(G, matching_link_value)
    core = core_bounds(nodes, v)
    nuc = nucleolus(nodes, v)
    bal, M = balanced_dynamics(G)
    btw = nx.betweenness_centrality(G, normalized=True)
    deg = dict(G.degree())
    results[name] = dict(
        v_N=v[frozenset(nodes)],
        deals_per_round=int(v[frozenset(nodes)] / PIE),
        myerson={x: round(phi[x], 3) for x in nodes},
        position_value={x: round(pos[x], 3) for x in nodes},
        core=core,
        nucleolus=nuc,
        balanced=bal,
        degree=deg,
        betweenness={x: round(btw[x], 3) for x in nodes},
    )
    assert abs(sum(phi.values()) - v[frozenset(nodes)]) < 1e-6
    assert abs(sum(pos.values()) - v[frozenset(nodes)]) < 1e-6

print("=== EXCHANGE NETWORKS (24-point pies, 1-exchange) ===")
for name, r in results.items():
    print(f"\n[{name}] total per round = {r['v_N']:.0f} ({r['deals_per_round']} deal(s))")
    print("  node  deg  btw    Myerson  pos.value  nucleolus  balanced  core[min,max]")
    for x in r["myerson"]:
        core = r["core"][x] if r["core"] else "EMPTY"
        bal = r["balanced"][x] if r["balanced"] else "none"
        print(f"  {x:4s}  {r['degree'][x]:3d}  {r['betweenness'][x]:5.3f}  {r['myerson'][x]:7.3f}  "
              f"{r['position_value'][x]:9.3f}  {r['nucleolus'][x]:9.3f}  {str(bal):8s}  {core}")

# Per-deal share of the hub in stars / path3 (hub trades every round with one leaf)
print("\n=== Hub's share of each 24-point deal (stars; dyad = 1 leaf) ===")
for k, name in [(1, "dyad"), (2, "path3"), (3, "star3"), (4, "star4"), (5, "star5")]:
    r = results[name]
    hub = "A" if name == "dyad" else ("B" if name == "path3" else "H")
    my = r["myerson"][hub]
    pv = r["position_value"][hub]
    print(f"  k={k} leaves: Myerson hub = {my:.2f} pts/round = {my/PIE:.1%} of each deal; "
          f"position value hub = {pv:.2f} ({pv/PIE:.1%}); "
          f"core hub = {r['core'][hub]}; closed form k/(k+1) = {k/(k+1):.1%}")

# Broker (relay) networks: A and C can only reach each other through brokers
print("\n=== BROKER NETWORKS (Myerson's communication-restricted game) ===")
brokers = {}
for m in range(1, 5):
    edges = []
    for j in range(m):
        edges += [("A", f"B{j+1}"), (f"B{j+1}", "C")]
    brokers[f"parallel_{m}"] = make(edges)
brokers["serial_2"] = make([("A", "B1"), ("B1", "B2"), ("B2", "C")])
brokers["serial_3"] = make([("A", "B1"), ("B1", "B2"), ("B2", "B3"), ("B3", "C")])
broker_results = {}
for name, G in brokers.items():
    nodes = list(G.nodes())
    v = build_v(G, broker_value)
    phi = shapley(nodes, v)
    pos = position_value(G, broker_link_value)
    core = core_bounds(nodes, v)
    broker_results[name] = dict(myerson={x: round(phi[x], 3) for x in nodes},
                                position_value={x: round(pos[x], 3) for x in nodes}, core=core)
    print(f"\n[{name}]")
    for x in nodes:
        print(f"  {x:3s} Myerson={phi[x]:6.3f}  position value={pos[x]:6.3f}  "
              f"core={core[x] if core else 'EMPTY'}")
    bsum = sum(phi[x] for x in nodes if x.startswith("B"))
    psum = sum(pos[x] for x in nodes if x.startswith("B"))
    print(f"  brokers jointly: Myerson {bsum:.3f} of 24 ({bsum/PIE:.1%}); "
          f"position value {psum:.3f} ({psum/PIE:.1%})")

with open("predictions.json", "w") as f:
    json.dump({"exchange": {k: {kk: (vv if not isinstance(vv, dict) else {str(a): b for a, b in vv.items()})
                                for kk, vv in r.items()} for k, r in results.items()},
               "broker": {k: {kk: {str(a): b for a, b in vv.items()} if vv else None
                              for kk, vv in r.items()} for k, r in broker_results.items()}},
              f, indent=1, default=str)
print("\nSaved predictions.json")
