"""Draw Figure B1 from tracked network definitions, matching the supplied layout."""
import json
from context import FIGURES
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from llm_network_bargaining.networks import get_network


def draw():
    networks = ['pair', 'line3', 'line4', 'line5', 'star3', 'star4', 'stem', 'triangle']
    names = ['Pair', 'Three-node line', 'Four-node line', 'Five-node line',
             'Three-leaf star', 'Four-leaf star', 'Stem', 'Triangle']
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'svg.fonttype': 'none',
                         'svg.hashsalt': 'sprint-network-topologies', 'figure.facecolor': 'white'})
    fig, axes = plt.subplots(2, 4, figsize=(6.5, 2.05))
    fig.subplots_adjust(left=.02, right=.98, top=.88, bottom=.04, hspace=.54, wspace=.18)
    records = []
    for net, title, ax in zip(networks, names, axes.flat):
        network = get_network(net)
        if net in ['pair', 'line3', 'line4', 'line5']:
            half = {'pair': .33, 'line3': .66, 'line4': .90, 'line5': .96}[net]
            pos = {n: (float(x), 0) for n, x in zip(network.nodes, np.linspace(-half, half, len(network.nodes)))}
        elif net == 'star3':
            pos = {'H': (0, 0), 'L1': (0, .78), 'L2': (-.78, -.64), 'L3': (.78, -.64)}
        elif net == 'star4':
            pos = {'H': (0, 0), 'L1': (0, .78), 'L2': (.78, 0), 'L3': (0, -.78), 'L4': (-.78, 0)}
        elif net == 'stem':
            pos = {'A': (-.90, 0), 'B': (-.15, 0), 'C': (.78, .68), 'D': (.78, -.68)}
        else:
            pos = {'A': (0, .78), 'B': (-.78, -.68), 'C': (.78, -.68)}
        for a, b in network.edges:
            ax.plot([pos[a][0], pos[b][0]], [pos[a][1], pos[b][1]], color='#242424', lw=.85, zorder=1)
        for node, (x, y) in pos.items():
            ax.plot(x, y, 'o', ms=10, mfc='white', mec='#242424', mew=.7, zorder=2)
            ax.text(x, y, node, ha='center', va='center', fontsize=6.8, zorder=3)
        ax.set_title(title, fontsize=8, pad=4)
        ax.set(xlim=(-1.17, 1.17), ylim=(-1.02, 1.15))
        ax.axis('off')
        records.append(dict(network=net, nodes=list(network.nodes), links=[list(e) for e in network.edges], positions=pos))
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    outside = [t.get_text() for ax in axes.flat for t in [ax.title, *ax.texts]
               if not fig.bbox.contains(*t.get_window_extent(renderer).get_points()[0])
               or not fig.bbox.contains(*t.get_window_extent(renderer).get_points()[1])]
    assert not outside, outside
    for ext in ['png', 'svg', 'pdf']:
        metadata = {'Software': None} if ext == 'png' else {'Creator': None, 'Date': None} if ext == 'svg' else {'Creator': None, 'CreationDate': None, 'ModDate': None}
        fig.savefig(FIGURES / ('figure_b1_networks.' + ext), dpi=240, metadata=metadata)
    (FIGURES / 'network_topologies.json').write_text(json.dumps(dict(width_inches=6.5, height_inches=2.05, minimum_label_pt=6.8, text_outside_canvas=outside, networks=records), indent=2) + '\n')
    plt.close(fig)


if __name__ == '__main__':
    draw()
