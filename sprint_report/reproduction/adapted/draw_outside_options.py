from pathlib import Path
import json,hashlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import networkx as nx
from context import ROOT,DATA,FIGURES as OUT
from llm_network_bargaining.networks import get_network

INK,BLUE,PALE,GREY='#222222','#0072B2','#dceaf3','#b9b9b9'
REFERENCES={'line4':{'A':8,'B':16,'C':16,'D':8}}
def positions(name):
    net = get_network(name)
    if name in ["pair", "line3", "line4", "line5"]:
        spacing = 1.0 if name == "line5" else 1.2
        return {v: ((i - (len(net.nodes) - 1) / 2) * spacing, 0)
                for i, v in enumerate(net.nodes)}
    if name == "star3":
        return {"H": (0, 0), "L1": (0, 1.1), "L2": (-1.4, -.9), "L3": (1.4, -.9)}
    if name == "star4":
        return {"H": (0, 0), "L1": (0, 1.2), "L2": (1.5, 0),
                "L3": (0, -1.2), "L4": (-1.5, 0)}
    if name == "stem":
        return {"A": (-1.8, 0), "B": (-.3, 0), "C": (1.4, 1), "D": (1.4, -1)}
    return {"A": (0, 1.1), "B": (-1.4, -1), "C": (1.4, -1)}

def draw_graph(ax, name, nodes=None, edges=None, matching=(), node_values=None, edge_values=None):
    net = get_network(name)
    pos = positions(name)
    present = set(net.nodes if nodes is None else nodes)
    available = set(net.edges if edges is None else edges)
    active = [edge for edge in net.edges if edge in available and set(edge) <= present]
    absent = [edge for edge in net.edges if edge not in active]
    if absent:
        nx.draw_networkx_edges(net.graph(), pos, ax=ax, edgelist=absent,
                               edge_color="#d3d3d3", width=1.2, style="dashed")
    if active:
        nx.draw_networkx_edges(net.graph(), pos, ax=ax, edgelist=active,
                               edge_color=INK, width=1.7)
    if matching:
        assert set(matching) <= set(active)
        nx.draw_networkx_edges(net.graph(), pos, ax=ax, edgelist=matching,
                               edge_color=BLUE, width=4)
    nx.draw_networkx_nodes(net.graph(), pos, ax=ax, nodelist=list(net.nodes),
                          node_size=850 if node_values else 530,
                          node_color=[PALE if node in present else "#fafafa" for node in net.nodes],
                          edgecolors=[INK if node in present else GREY for node in net.nodes],
                          linewidths=1.2)
    for node, (x, y) in pos.items():
        label = node if node_values is None else f"{node}\n{node_values[node]:g}"
        ax.text(x, y, label, ha="center", va="center", fontsize=12,
                color=INK if node in present else GREY, linespacing=1.15)
    if edge_values:
        nx.draw_networkx_edge_labels(net.graph(), pos, ax=ax,
                                    edge_labels={edge: f"{value:g}" for edge, value in edge_values.items()},
                                    rotate=False, font_size=12, font_color=INK,
                                    bbox={"facecolor": "white", "edgecolor": "none", "pad": 2})
    ax.set(xlim=(-2.5, 2.5), ylim=(-1.45, 1.45), aspect="equal")
    ax.set_axis_off()
    if name in ("line3", "line4", "line5"):
        ax.set_ylim(-.6, .6)

def outside_options(net, points, matching):
    partner = {a: b for a, b in matching} | {b: a for a, b in matching}
    result = {}
    for node in net.nodes:
        alternatives = [other for edge in net.edges if node in edge
                        for other in edge if other != node and other != partner.get(node)]
        result[node] = max([0] + [net.pie - points[other] for other in alternatives])
    return result

def save(fig, name):
    fig.savefig(OUT / f"{name}.png", dpi=200, facecolor="white", bbox_inches="tight",
                metadata={"Software": None})
    fig.savefig(OUT / f"{name}.svg", facecolor="white", bbox_inches="tight",
                metadata={"Date": None, "Creator": None})
    plt.close(fig)

def four_line_options():
    points = REFERENCES["line4"]
    net = get_network("line4")
    matching = (("A", "B"), ("C", "D"))
    alternatives = outside_options(net, points, matching)
    gains = {node: points[node] - alternatives[node] for node in net.nodes}
    fig = plt.figure(figsize=(10, 4.5))
    fig.suptitle("Four-node line: equal gains above unequal outside options", y=.985, fontsize=16)
    fig.text(.5, .875, "A–B and C–D trade; B–C remains an alternative.", ha="center", fontsize=12)
    ax = fig.add_axes((.21, .60, .77, .19))
    draw_graph(ax, "line4", matching=matching)
    ax.set_aspect("auto")
    xs = {node: .21 + .77 * (x + 2.5) / 5 for node, (x, _) in positions("line4").items()}
    for y, label, values in ((.48, "Payoff", points), (.32, "Outside option", alternatives),
                              (.16, "Gain above option", gains)):
        fig.text(.035, y, label, ha="left", va="center", fontsize=12)
        for node in net.nodes:
            fig.text(xs[node], y, str(values[node]), ha="center", va="center", fontsize=13)
    save(fig, "appendix_i_four_line_outside_options")

if __name__=='__main__':
 from llm_network_bargaining.theory import balanced_outcome
 assert balanced_outcome(get_network('line4'))==REFERENCES['line4']
 plt.rcParams.update({'font.family':'DejaVu Sans','font.size':12,'svg.fonttype':'none','svg.hashsalt':'appendix-i-core-balance-guide'})
 four_line_options()
 for ext in ['png','svg']:(OUT/('appendix_i_four_line_outside_options.'+ext)).replace(OUT/('figure_d2_outside_options.'+ext))
 points=REFERENCES['line4'];options=outside_options(get_network('line4'),points,(('A','B'),('C','D')))
 assert options=={'A':0,'B':8,'C':8,'D':0}
 assert all(points[n]-options[n]==8 for n in points)
 (OUT/'figure_d2_coordinates.json').write_text(json.dumps(dict(points=points,outside_options=options,gains={n:points[n]-options[n] for n in points}),indent=2)+'\n')
