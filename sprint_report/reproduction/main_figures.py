"""Draw the two main figures from freshly recomputed saved-log summaries."""
from pathlib import Path
import csv
import hashlib
import json
import os
import sys

from context import ROOT, PROJECT, OUT as RESULTS, DATA, FIGURES

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.text import Text
import numpy as np
import pandas as pd

from llm_network_bargaining.networks import get_network

OUT = FIGURES
OUT.mkdir(parents=True, exist_ok=True)
NETS = ["pair", "line3", "line4", "line5", "star3", "star4", "stem", "triangle"]
TITLES = dict(zip(NETS, ["Pair", "Three-node line", "Four-node line", "Five-node line",
                         "Three-leaf star", "Four-leaf star", "Stem", "Triangle"]))
ARMS = {"full_map": ("Full map", "#242424"), "own_links": ("Own links", "#C65B2A")}
LINK_DATA = DATA / "completed_links"
EARN_DATA = DATA / "section_6"
edges = pd.read_csv(LINK_DATA / "edge_summary.csv").query("window == 'primary'")
edge_refs = pd.read_csv(LINK_DATA / "edge_references.csv")
summary = pd.read_csv(EARN_DATA / "main_earnings_summary.csv")
episodes = pd.read_csv(EARN_DATA / "main_earnings_episodes.csv")
plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none",
                     "svg.hashsalt": "sprint-phase2", "figure.facecolor": "white",
                     "axes.spines.top": False, "axes.spines.right": False})
coordinates = []
dimensions = []


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(fig, name, minimum_label):
    fig.canvas.draw()
    width, height = fig.get_size_inches()
    renderer = fig.canvas.get_renderer()
    bounds = fig.bbox
    outside = []
    visible_text = list(fig.texts)
    for ax in fig.axes:
        visible_text.extend(ax.texts)
        visible_text.append(ax.title)
        if ax.axison:
            visible_text.extend(ax.get_xticklabels())
            visible_text.extend(ax.get_yticklabels())
    for text in visible_text:
        if not text.get_visible() or not text.get_text():
            continue
        box = text.get_window_extent(renderer)
        if box.x0 < bounds.x0 - 1 or box.y0 < bounds.y0 - 1 or box.x1 > bounds.x1 + 1 or box.y1 > bounds.y1 + 1:
            outside.append(text.get_text())
    for ext in ("png", "svg", "pdf"):
        metadata = {"Software": None} if ext == "png" else {"Creator": None, "Date": None} if ext == "svg" else {"Creator": None, "CreationDate": None, "ModDate": None}
        fig.savefig(OUT / f"{name}.{ext}", dpi=240, metadata=metadata)
    dimensions.append(dict(figure=name, width_inches=float(width), height_inches=float(height),
                           minimum_label_pt=minimum_label, text_outside_canvas=outside))
    plt.close(fig)


def topology(net):
    if net in ("pair", "line3", "line4", "line5"):
        nodes = get_network(net).nodes
        return {node: (x, 0.50) for node, x in zip(nodes, np.linspace(0.075, .925, len(nodes)))}
    if net == "star3":
        return {"H": (.48, .50), "L1": (.88, .87), "L2": (.08, .50), "L3": (.88, .13)}
    if net == "star4":
        return {"H": (.50, .50), "L1": (.90, .87), "L2": (.10, .87), "L3": (.10, .13), "L4": (.90, .13)}
    if net == "stem":
        return {"A": (.075, .50), "B": (.43, .50), "C": (.89, .87), "D": (.89, .13)}
    return {"A": (.10, .13), "B": (.50, .87), "C": (.90, .13)}


def label_position(net, a, b, i, positions):
    x = (positions[a][0] + positions[b][0]) / 2
    y = (positions[a][1] + positions[b][1]) / 2
    if net in ("pair", "line3"):
        return x, .77
    if net in ("line4", "line5"):
        return x, .79 if i % 2 == 0 else .21
    if net == "star3":
        return {"L1": (.63, .84), "L2": (.23, .75), "L3": (.63, .16)}[b]
    if net == "star4":
        return {"L1": (.78, .62), "L2": (.22, .62), "L3": (.22, .38), "L4": (.78, .38)}[b]
    if net == "stem":
        return {("A", "B"): (.15, .77), ("B", "C"): (.57, .84),
                ("B", "D"): (.57, .16), ("C", "D"): (.90, .50)}[(a, b)]
    return {("A", "B"): (.23, .57), ("A", "C"): (.50, .12), ("B", "C"): (.77, .57)}[(a, b)]


def completed_links():
    fig = plt.figure(figsize=(6.5, 6.15))
    fig.text(.5, .983, "Which links carry completed deals?", ha="center", va="top", fontsize=11, weight="bold")
    fig.text(.5, .946, "Rounds 13–24 · 120 network-rounds per network and setting", ha="center", va="top", fontsize=8)
    fig.text(.5, .913, "Labels: observed % above (uniform-reference %) · width = observed frequency", ha="center", va="top", fontsize=7.5)
    grid = fig.add_gridspec(4, 4, left=.015, right=.985, top=.825, bottom=.040,
                           hspace=.27, wspace=.16, height_ratios=[.83, .93, 1.32, 1.27])
    for index, net in enumerate(NETS):
        row, pair = divmod(index, 2)
        for arm_index, (arm, (title, colour)) in enumerate(ARMS.items()):
            ax = fig.add_subplot(grid[row, pair * 2 + arm_index])
            pos = topology(net)
            group = edges[edges.network_id.eq(net) & edges.knowledge.eq(arm)].sort_values("edge")
            for i, entry in enumerate(group.itertuples()):
                a, b = entry.edge.split("–")
                frequency = float(entry.deal_frequency)
                reference = float(edge_refs[edge_refs.network_id.eq(net) & edge_refs.edge.eq(entry.edge)].frequency_reference.iloc[0])
                ax.plot([pos[a][0], pos[b][0]], [pos[a][1], pos[b][1]],
                        lw=.65 + 2.65 * frequency if frequency else .65,
                        color=colour if frequency else "#999999", ls="-" if frequency else (0, (3, 2)), zorder=1)
                x, y = label_position(net, a, b, i, pos)
                ax.text(x, y, f"{100*frequency:.1f}%\n({100*reference:.1f}%)", ha="center", va="center",
                        fontsize=7.5, linespacing=1.05, bbox=dict(facecolor="white", edgecolor="none", pad=.15), zorder=3)
                coordinates.append(dict(figure="completed_links", network_id=net, knowledge=arm,
                                        edge=entry.edge, observed=frequency, reference=reference))
            for node, (x, y) in pos.items():
                ax.plot(x, y, "o", ms=10.0, mfc="white", mec=colour, mew=.9, zorder=4)
                ax.text(x, y, node, ha="center", va="center", fontsize=7.5, zorder=5)
            ax.set_title(f"{TITLES[net]}\n{title}", fontsize=8, linespacing=1.2, color=colour, pad=4)
            ax.set(xlim=(-.045, 1.045), ylim=(-.02, 1.02))
            ax.axis("off")
    fig.text(.5, .014, "Black: full map · orange: own links · dashed grey: permitted link with no completed deal", ha="center", va="bottom", fontsize=7.5)
    save(fig, "figure_1_completed_links", 7.5)


def earnings():
    nets = ["line3", "line4", "line5", "star3", "star4", "stem"]
    classes = {"line3": ["A|C", "B"], "line4": ["A|D", "B|C"], "line5": ["A|E", "B|D", "C"],
               "star3": ["H", "L1|L2|L3"], "star4": ["H", "L1|L2|L3|L4"], "stem": ["A", "B", "C|D"]}
    refs = [("equal_split", "Equal-split earnings", "#777777", "x"),
            ("myerson", "Myerson value", "#0072B2", "^"),
            ("position_value", "Position value", "#AA3377", "D"),
            ("balanced", "Balanced outcome", "#009E73", "*")]
    fig, axes = plt.subplots(3, 2, figsize=(6.5, 4.7), sharey=True)
    fig.suptitle("Observed earnings and four theoretical references", fontsize=11, y=.985, weight="bold")
    fig.text(.5, .935, "Full map · rounds 13–24 · ten episodes per network", ha="center", fontsize=8)
    handles = [Line2D([], [], color="#242424", marker="o", ls="none", ms=4, label="Observed mean"),
               Line2D([], [], color="#242424", alpha=.4, marker="o", ls="none", ms=2.5, label="Individual episode")]
    handles += [Line2D([], [], color=c, marker=m, ls="none", ms=5 if m=="*" else 4, label=label) for _,label,c,m in refs]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, .905), ncol=3,
               frameon=False, fontsize=7.5, columnspacing=1.4, handletextpad=.5)
    for ax, net in zip(axes.flat, nets):
        for i, node_class in enumerate(classes[net]):
            group = episodes[episodes.network_id.eq(net) & episodes.node_class.eq(node_class)].sort_values("episode_uid")
            entry = summary[summary.network_id.eq(net) & summary.node_class.eq(node_class)].iloc[0]
            ax.scatter(i-.22+np.linspace(-.065,.065,len(group)), group.points_mean, color="#242424", s=9, alpha=.35, linewidths=0, zorder=3)
            ax.plot(i-.22, entry.points_mean, "o", color="#242424", ms=4, zorder=5)
            for point in group.itertuples():
                coordinates.append(dict(figure="earnings_episode", network_id=net, knowledge="full_map", node_class=node_class,
                                        episode_uid=point.episode_uid, value=float(point.points_mean)))
            coordinates.append(dict(figure="earnings_mean",network_id=net,knowledge="full_map",node_class=node_class,value=float(entry.points_mean)))
            for offset, (field, label, colour, marker) in zip([.04,.17,.30,.43], refs):
                ax.plot(i+offset, entry[field], color=colour, marker=marker, ls="none", ms=6 if marker=="*" else 4.5, mew=.8)
                coordinates.append(dict(figure="earnings_reference",network_id=net,node_class=node_class,reference=field,value=float(entry[field])))
        labels = ["Leaves" if cl.startswith("L1") else cl.replace("|", ", ") for cl in classes[net]]
        ax.set(title=TITLES[net], xticks=np.arange(len(labels))+.1, xticklabels=labels,
               xlim=(-.5,len(labels)-.38), ylim=(-.7,25.2), yticks=[0,6,12,18,24])
        ax.title.set_fontsize(9)
        ax.tick_params(labelsize=8)
        ax.grid(axis="y", color="#dddddd", lw=.45)
    fig.text(.012, .44, "Mean points per agent per round", rotation=90, va="center", fontsize=8.5)
    fig.subplots_adjust(left=.085,right=.99,top=.755,bottom=.075,hspace=.62,wspace=.22)
    save(fig, "figure_2_earnings", 7.5)


if __name__ == "__main__":
    completed_links()
    earnings()
    (OUT / "coordinates.json").write_text(json.dumps(coordinates, indent=2)+"\n")
    inputs = [LINK_DATA/"edge_summary.csv", LINK_DATA/"edge_references.csv",
              EARN_DATA/"main_earnings_summary.csv", EARN_DATA/"main_earnings_episodes.csv"]
    manifest = dict(scope="Plot presentation from freshly recomputed outputs; no additional inference", dimensions=dimensions,
                    script_sha256=sha(Path(__file__)), inputs={str(p.relative_to(ROOT)):sha(p) for p in inputs},
                    outputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and (p.name.startswith(("figure_1_", "figure_2_")) or p.name=="coordinates.json")})
    (OUT/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(json.dumps(dimensions, indent=2))
