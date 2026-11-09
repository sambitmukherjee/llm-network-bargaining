"""Verbatim selected archive helpers; globals supplied by selected_analysis.py."""


def independent_theory(network):
    """Enumerate arrival orders using NetworkX rather than the theory helpers."""
    net = get_network(network)

    @cache
    def node_worth(nodes):
        return 24 * len(nx.max_weight_matching(net.graph().subgraph(nodes), maxcardinality=True))

    node_credit = dict.fromkeys(net.nodes, 0)
    for order in permutations(net.nodes):
        present = frozenset()
        for node in order:
            expanded = present | {node}
            node_credit[node] += node_worth(expanded) - node_worth(present)
            present = expanded
    node_credit = {k: v / factorial(len(net.nodes)) for k, v in node_credit.items()}

    @cache
    def link_worth(edges):
        graph = nx.Graph()
        graph.add_nodes_from(net.nodes)
        graph.add_edges_from(edges)
        return 24 * len(nx.max_weight_matching(graph, maxcardinality=True))

    link_credit = dict.fromkeys(net.edges, 0)
    for order in permutations(net.edges):
        present = frozenset()
        for edge in order:
            expanded = present | {edge}
            link_credit[edge] += link_worth(expanded) - link_worth(present)
            present = expanded
    position = {node: sum(v for edge, v in link_credit.items() if node in edge)
                / (2 * factorial(len(net.edges))) for node in net.nodes}
    matchings = [edges for edges in combinations(net.edges, max_deals(net))
                 if len({v for edge in edges for v in edge}) == 2 * len(edges)]
    equal = {node: 12 * sum(any(node in edge for edge in matching) for matching in matchings)
             / len(matchings) for node in net.nodes}
    return node_credit, position, equal, len(matchings)


def ci(values):
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    lo, hi = np.quantile(x, [.025, .975]) if len(x) else [np.nan, np.nan]
    return dict(ci_low=float(lo), ci_high=float(hi), n_defined_bootstrap=len(x))


def resample(values, *key):
    """Rows are whole episodes; any columns travel together in each draw."""
    x = np.asarray(values, dtype=float)
    rng = make_rng(derive_seed(SEED, 'study_phase4', *key))
    indices = rng.integers(len(x), size=(BOOT, len(x)))
    return np.nanmean(x[indices], axis=1)


def independent_classes(rows, start, end):
    sub = rows[rows['round'].between(start, end)]
    meta = ['episode_uid', 'config_name', 'condition_key', 'network_id', 'knowledge',
            'assignment', 'episode_index']
    nodes = sub.groupby(meta+['node_class', 'node'], as_index=False).agg(
        points_mean=('points', 'mean'), deal_rate=('dealt', 'mean'),
        share_mean=('share', 'mean'), n_deals=('dealt', 'sum'))
    classes = nodes.groupby(meta+['node_class'], as_index=False).agg(
        points_mean=('points_mean', 'mean'), deal_rate=('deal_rate', 'mean'),
        share_mean=('share_mean', 'mean'), n_defined_share_members=('share_mean', 'count'),
        n_members=('node', 'size'))
    return nodes, classes


def audit_nulls(classes, pui, canonical, window):
    """Reconstruct statistics and saved RNG assignments without test helpers."""
    audits, deviations = [], []
    full = classes[classes.knowledge.eq('full_map')]
    for net in H1_NETS:
        group = full[full.network_id.eq(net)&full.node_class.eq(FOCI[net])].sort_values('episode_uid')
        values = group.share_mean.to_numpy(); d = values-.5
        signs = np.array(list(product([-1, 1], repeat=len(d))))
        null = (signs*np.abs(d)).mean(axis=1)
        observed = d.mean(); tail = int(np.sum(null >= observed-1e-12))
        saved = canonical['results']['H1']['per_network'][net]
        check(f'{window} H1 {net}: exact sign-flip tail and statistic',
              tail/len(null)==saved['p_value'] and np.isclose(observed,saved['statistic'],atol=1e-14,rtol=0))
        check(f'{window} H1 {net}: ten positive episode deviations',len(d)==10 and (d>0).all())
        audits.append(dict(window=window,test='H1/'+net,observed_statistic=observed,
                           method='exact',n_assignments=len(null),tail_count=tail,p_value=tail/len(null),
                           assignment_space=2**len(d)))
        ARRAYS[f'{window}_H1_{net}_null'] = null
        deviations.extend(dict(window=window,network_id=net,episode_uid=uid,
                               share=float(value),deviation=float(value-.5))
                          for uid,value in zip(group.episode_uid,values))

    # Preserve the source helper's episode order and RNG batching, but compute
    # the slope directly as a covariance divided by centred leaf-count squares.
    stars = full[full.network_id.isin(LEAVES)&full.apply(lambda r:r.node_class==FOCI[r.network_id],axis=1)].copy()
    stars = stars.sort_values(['network_id','episode_uid'])
    values = stars.share_mean.to_numpy(); k = stars.network_id.map(LEAVES).to_numpy(dtype=float)
    centered = k-k.mean(); denominator = centered@centered
    observed = float(centered@values/denominator)
    rng = make_rng(derive_seed(derive_seed(SEED,'H3'),'slope'))
    batches=[]
    for start in range(0,200000,2048):
        shuffled=rng.permuted(np.tile(values,(min(2048,200000-start),1)),axis=1)
        batches.append((shuffled@centered)/denominator)
    null=np.concatenate(batches);tail=int(np.sum(null>=observed-1e-12))
    saved=canonical['results']['H3']
    check(f'{window} H3: Monte Carlo assignments reproduce tail and slope',
          (tail+1)/(len(null)+1)==saved['p_value'] and np.isclose(observed,saved['statistic'],rtol=0,atol=1e-14))
    space=factorial(30)//factorial(10)**3
    audits.append(dict(window=window,test='H3',observed_statistic=observed,method='monte_carlo',
                       n_assignments=len(null),tail_count=tail,p_value=(tail+1)/(len(null)+1),assignment_space=space))
    ARRAYS[f'{window}_H3_null']=null

    ends4=full[full.network_id.eq('line4')&full.node_class.eq('A|D')].sort_values('episode_uid').points_mean.to_numpy()
    ends5=full[full.network_id.eq('line5')&full.node_class.eq('A|E')].sort_values('episode_uid').points_mean.to_numpy()
    values=np.r_[ends5,ends4]; observed=float(ends4.mean()-ends5.mean())
    null=np.array([2*values[list(indices)].mean()-values.mean()*2
                   for indices in combinations(range(20),10)])
    tail=int(np.sum(null>=observed-1e-12));saved=canonical['results']['H4']
    check(f'{window} H4: independently enumerated 184756 assignments reproduce result',
          tail/len(null)==saved['p_value'] and np.isclose(observed,saved['statistic'],atol=1e-12,rtol=0))
    check(f'{window} H4: every four-line episode exceeds every five-line episode',ends4.min()>ends5.max())
    audits.append(dict(window=window,test='H4',observed_statistic=observed,method='exact',
                       n_assignments=len(null),tail_count=tail,p_value=tail/len(null),assignment_space=comb(20,10)))
    ARRAYS[f'{window}_H4_null']=null

    # The source helper concatenates full-map episodes before own-links episodes
    # and shuffles within sorted network strata. No episode crosses a network.
    combined=pd.concat([pui[pui.knowledge.eq('full_map')],pui[pui.knowledge.eq('own_links')]])
    groups=[combined[combined.network_id.eq(net)].pui.to_numpy() for net in sorted(ELIGIBLE)]
    observed=float(np.mean([x[:10].mean()-x[10:].mean() for x in groups]))
    rng=make_rng(derive_seed(derive_seed(SEED,'H5'),'stratified'));batches=[]
    for start in range(0,100000,2048):
        count=min(2048,100000-start);scores=np.zeros(count)
        for values in groups:
            shuffled=rng.permuted(np.tile(values,(count,1)),axis=1)
            scores+=shuffled[:,:10].mean(axis=1)-shuffled[:,10:].mean(axis=1)
        batches.append(scores/6)
    null=np.concatenate(batches);tail=int(np.sum(abs(null)>=abs(observed)-1e-12));saved=canonical['results']['H5']
    check(f'{window} H5: stratified Monte Carlo assignments reproduce tail and contrast',
          (tail+1)/(len(null)+1)==saved['p_value'] and np.isclose(observed,saved['statistic'],atol=1e-14,rtol=0))
    audits.append(dict(window=window,test='H5',observed_statistic=observed,method='monte_carlo',
                       n_assignments=len(null),tail_count=tail,p_value=(tail+1)/(len(null)+1),assignment_space=comb(20,10)**6))
    ARRAYS[f'{window}_H5_null']=null
    return audits,deviations
