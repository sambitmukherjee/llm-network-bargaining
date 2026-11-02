"""Publication figures using the Phase 6 episode metrics and bootstrap CIs."""

from collections.abc import Sequence
from math import ceil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
import numpy as np

from ..networks import get_network, list_networks
from ..seeds import derive_seed, make_rng
from ..structure import class_of
from .data import Dataset
from .gate import select_configs
from .metrics import (condition_class_summary, episode_class_metrics, learning_curves,
                      power_use, summarise_power_use)
from .predictions import BENCHMARKS, advantaged_class, class_predictions

matplotlib.rcParams.update({
    "svg.hashsalt": "lnb", "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.grid": True, "axes.axisbelow": True, "grid.color": "#dddddd", "grid.linewidth": .5,
    "font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
})

# Okabe--Ito colours; shapes also distinguish every benchmark.
COLOURS = {"equal_split": "#0072B2", "myerson": "#E69F00", "position_value": "#CC79A7", "balanced": "#009E73"}
MARKERS = {"equal_split": "o", "myerson": "^", "position_value": "D", "balanced": "*"}
LABELS = {"equal_split": "Equal split", "myerson": "Myerson", "position_value": "Position value", "balanced": "Balanced"}
KNOWLEDGE = {"full_map": ("Full map", "#0072B2", "o"), "own_links": ("Own links", "#D55E00", "s")}
HUBS = {"line3": ("B", 2), "star3": ("H", 3), "star4": ("H", 4), "star5": ("H", 5)}
POWER_NETWORKS = ("line3", "line4", "line5", "star3", "star4", "stem")


def _networks(ids: Sequence[str]) -> list[str]:
    """Keep registry order, independently of log and DataFrame order."""
    return [net.id for net in list_networks() if net.id in ids]


def _panels(networks: list[str]) -> tuple[Figure, list[Axes]]:
    """Make only the axes that contain data, without empty padding panels."""
    count = max(1, len(networks))
    columns = min(3, count)
    fig = plt.figure(figsize=(4 * columns, 3.4 * ceil(count / columns)), layout="constrained")
    return fig, [fig.add_subplot(ceil(count / columns), columns, i + 1) for i in range(count)]


def _dots(ax: Axes, x: float, values: Sequence[float], *, seed: int, label: str,
          colour: str = "#333333", scale: float = 1) -> None:
    """Jitter episodes horizontally; no randomness changes their y values."""
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    rng = make_rng(derive_seed(seed, "figure_jitter", label))
    points = ax.scatter(x + rng.uniform(-.045, .045, len(values)), values * scale,
                        s=13, alpha=.45, color=colour, linewidths=0, zorder=4, clip_on=False)
    points.set_gid(f"episodes:{label}")


def _mean_ci(ax: Axes, x: float, mean: float, low: float, high: float,
             colour: str = "black", marker: str = "o") -> None:
    """Draw the supplied mean and interval, including asymmetric intervals."""
    if np.isfinite([low, high]).all():
        ax.vlines(x, low, high, color=colour, linewidth=1.6, zorder=5)
        ax.hlines([low, high], x - .025, x + .025, color=colour, linewidth=1, zorder=5)
    ax.plot(x, mean, marker=marker, color=colour, markersize=5, linestyle="none", zorder=6, clip_on=False)


def _benchmark_handles() -> list[Line2D]:
    """Return explicit legend handles, even when a predictor is undefined."""
    return [Line2D([], [], color=COLOURS[name], marker=MARKERS[name], linestyle="none", label=LABELS[name])
            for name in BENCHMARKS]


def save_figure(fig: Figure, path_stem: str | Path) -> tuple[Path, Path]:
    """Save deterministic PNG (200 dpi) and SVG files, without timestamps."""
    stem = Path(path_stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    png, svg = Path(str(stem) + ".png"), Path(str(stem) + ".svg")
    fig.savefig(png, dpi=200, metadata={"Software": None})
    fig.savefig(svg, metadata={"Date": None, "Creator": None})
    return png, svg


def fig_observed_vs_predicted(ds: Dataset, config: str = "minimum_study", window: str = "second_half",
                              seed: int = 1, n_boot: int = 2000) -> Figure:
    """F1: episode class points, their mean/CI, and four point predictions."""
    selected = select_configs(ds, [config])
    episodes = episode_class_metrics(selected, window)
    summary = condition_class_summary(selected, window, n_boot, seed)
    networks = _networks(list(episodes.network_id.unique()))
    fig, axes = _panels(networks)
    if len(networks) <= 1:
        # The control has one panel: leave room for all six legend entries.
        fig.set_size_inches(7.5, 4.5)
    for ax, network in zip(axes, networks):
        group = summary[summary.network_id == network]
        classes = list(class_predictions(network).node_class)
        for x, label in enumerate(classes):
            row = group[group.node_class == label].iloc[0]
            values = episodes[(episodes.network_id == network) & (episodes.node_class == label)].points_mean
            _dots(ax, x - .22, values, seed=seed, label=f"F1/{network}/{label}")
            _mean_ci(ax, x - .22, row.points_mean, row.points_mean_ci_low, row.points_mean_ci_high)
            for offset, name in zip((-.07, .05, .17, .29), BENCHMARKS):
                if np.isfinite(row[name]):
                    ax.plot(x + offset, row[name], marker=MARKERS[name], color=COLOURS[name], linestyle="none", markersize=6, clip_on=False)
            if np.isfinite(row.core_min):
                ax.vlines(x + .39, row.core_min, row.core_max, color="#777777", linewidth=1)
                if row.core_min == row.core_max:
                    ax.plot(x + .39, row.core_min, marker="_", color="#777777", linestyle="none", clip_on=False)
        n = selected.episodes[selected.episodes.network_id == network].episode_uid.nunique()
        ax.set(title=f"{network} · n = {n}", xlabel="Node class", ylabel="Points per round", ylim=(0, 24))
        ax.set_xticks(range(len(classes)), classes)
        ax.set_yticks([0, 6, 12, 18, 24])
        ax.set_xlim(-.5, len(classes) - .5)
    fig.legend(handles=[Line2D([], [], color="black", marker="o", label="Observed mean and 95% CI"),
                        *_benchmark_handles(), Line2D([], [], color="#777777", marker="|", linestyle="none", label="Core interval")],
               loc="outside lower center", ncol=2 if len(networks) <= 1 else 3)
    return fig


def fig_power_use(ds: Dataset, configs: Sequence[str] = ("minimum_study", "own_links_arm"),
                   window: str = "second_half", seed: int = 1, n_boot: int = 2000) -> Figure:
    """F2: knowledge-setting power use, theory indices and human reference points."""
    selected = select_configs(ds, configs)
    episodes = power_use(selected, window)
    summary = summarise_power_use(selected, window, n_boot, seed)
    fig, ax = plt.subplots(figsize=(10, 4.6), layout="constrained")
    handles = []
    for knowledge, offset in (("full_map", -.16), ("own_links", .16)):
        label, colour, marker = KNOWLEDGE[knowledge]
        handles.append(Line2D([], [], color=colour, marker=marker, label=label))
        for x, network in enumerate(POWER_NETWORKS):
            group = summary[(summary.network_id == network) & (summary.knowledge == knowledge)]
            for row in group.itertuples():
                values = episodes[(episodes.condition_key == row.condition_key)].pui
                _dots(ax, x + offset, values, seed=seed, label=f"F2/{network}/{knowledge}", colour=colour)
                _mean_ci(ax, x + offset, row.pui, row.pui_ci_low, row.pui_ci_high, colour, marker)
    ax.axhline(0, color="#555555", linestyle=":", linewidth=1, label="Equal split")
    ax.axhline(1, color="#555555", linestyle="--", linewidth=1, label="Core power")
    for x, network in enumerate(POWER_NETWORKS):
        prediction = advantaged_class(network)
        for offset, name in [(-.04, "myerson"), (.04, "position_value")]:
            index = (prediction[name] - 12) / (prediction["balanced"] - 12)
            ax.plot(x + offset, index, marker=MARKERS[name], color=COLOURS[name], linestyle="none", markersize=7, zorder=7)
    for network, value in [("line3", .92), ("line5", .5)]:
        artist, = ax.plot(POWER_NETWORKS.index(network), value, marker="X", color="#000000", linestyle="none", markersize=8, zorder=8)
        artist.set_gid(f"human_anchor:{network}")
    band = Rectangle((POWER_NETWORKS.index("line4") - .27, .5), .54, .5,
                     facecolor="#000000", edgecolor="none", alpha=.12, zorder=1)
    band.set_gid("human_anchor:line4")
    ax.add_patch(band)
    counts = {network: [int(((selected.episodes.network_id == network) & (selected.episodes.knowledge == k)).sum())
                         for k in KNOWLEDGE] for network in POWER_NETWORKS}
    ax.set_xticks(range(6), [f"{net}\nn = {counts[net][0]} / {counts[net][1]}" for net in POWER_NETWORKS])
    ax.set(xlabel="Network (episode counts: full map / own links)", ylabel="Power-use index (unitless)", xlim=(-.6, 5.6))
    handles += [Line2D([], [], color=COLOURS[name], marker=MARKERS[name], linestyle="none", label=LABELS[name])
                for name in ("myerson", "position_value")]
    handles += [Line2D([], [], marker="X", color="#000000", linestyle="none", label="humans"),
                Line2D([], [], color="#555555", linestyle=":", label="0: equal split"),
                Line2D([], [], color="#555555", linestyle="--", label="1: core power")]
    fig.legend(handles=handles, loc="outside lower center", ncol=4)
    return fig


def fig_dose_response(ds: Dataset, config: str = "minimum_study", window: str = "second_half",
                       seed: int = 1, n_boot: int = 2000) -> Figure:
    """F3: hub shares for k=2 (line3), k=3, k=4, and optional k=5."""
    selected = select_configs(ds, [config])
    episodes = episode_class_metrics(selected, window)
    summary = condition_class_summary(selected, window, n_boot, seed)
    fig, ax = plt.subplots(figsize=(7, 4.5), layout="constrained")
    counts = {}
    for network, (hub, k) in HUBS.items():
        values = episodes[(episodes.network_id == network) & (episodes.node_class == hub)].share_mean
        if not len(values):
            continue
        counts[k] = len(values)
        row = summary[(summary.network_id == network) & (summary.node_class == hub)].iloc[0]
        _dots(ax, k, values, seed=seed, label=f"F3/{network}", scale=100)
        _mean_ci(ax, k, row.share_mean * 100, row.share_mean_ci_low * 100, row.share_mean_ci_high * 100)
    ks = np.arange(2, 6 if 5 in counts else 5)
    ax.plot(ks, 100 * ks / (ks + 1), color=COLOURS["myerson"], marker="^", label="Myerson k/(k+1)")
    ax.plot(ks, np.full(len(ks), 50), color=COLOURS["position_value"], marker="D", label="Position value and equal split")
    ax.plot(ks, np.full(len(ks), 100), color=COLOURS["balanced"], marker="*", label="Core")
    ax.set_xticks(ks, [f"{k}\nn = {counts.get(k, 0)}" for k in ks])
    ax.set(xlabel="Number of leaves k (2 = 3-line)", ylabel="Hub's per-deal share (%)", ylim=(0, 105))
    ax.legend(loc="lower right")
    return fig


def fig_parity_flip(ds: Dataset, config: str = "minimum_study", window: str = "second_half",
                     seed: int = 1, n_boot: int = 2000) -> Figure:
    """F4: observed end earnings with the four predictions for lines of 2--7."""
    selected = select_configs(ds, [config])
    episodes = episode_class_metrics(selected, window)
    summary = condition_class_summary(selected, window, n_boot, seed)
    fig, ax = plt.subplots(figsize=(8, 4.5), layout="constrained")
    predictions = {name: [] for name in BENCHMARKS}
    counts = {}
    for size in range(2, 8):
        network = "pair" if size == 2 else f"line{size}"
        net = get_network(network)
        ends = class_of(net)[net.nodes[0]]
        prediction = class_predictions(network).set_index("node_class").loc[ends]
        for name in BENCHMARKS:
            predictions[name].append(prediction[name])
        values = episodes[(episodes.network_id == network) & (episodes.node_class == ends)].points_mean
        if len(values):
            counts[size] = len(values)
            row = summary[(summary.network_id == network) & (summary.node_class == ends)].iloc[0]
            _dots(ax, size, values, seed=seed, label=f"F4/{network}")
            _mean_ci(ax, size, row.points_mean, row.points_mean_ci_low, row.points_mean_ci_high)
    for name in BENCHMARKS:
        ax.plot(range(2, 8), predictions[name], color=COLOURS[name], marker=MARKERS[name], label=LABELS[name], zorder=2, clip_on=False)
    ax.plot([], [], color="black", marker="o", linestyle="none", label="Observed mean and 95% CI")
    ax.set_xticks(range(2, 8), [f"{n}\nn = {counts[n]}" if n in counts else str(n) for n in range(2, 8)])
    ax.set(xlabel="Line length (nodes)", ylabel="End agents' points per round", ylim=(0, 24))
    ax.set_yticks([0, 6, 12, 18, 24])
    ax.legend(ncol=2)
    return fig


def fig_learning_curves(ds: Dataset, configs: Sequence[str] = ("pilot_full_map", "pilot_own_links"),
                         seed: int = 1, n_boot: int = 2000) -> Figure:
    """P1: advantaged-class power use over rounds, highlighting pilot windows."""
    selected = select_configs(ds, configs)
    curves = learning_curves(selected, n_boot=n_boot, seed=seed)
    networks = [net for net in _networks(list(curves.network_id.unique())) if advantaged_class(net) is not None]
    fig, axes = _panels(networks)
    for ax, network in zip(axes, networks):
        prediction = advantaged_class(network)
        denominator = prediction["balanced"] - 12
        for knowledge, (label, colour, marker) in KNOWLEDGE.items():
            group = curves[(curves.network_id == network) & (curves.node_class == prediction["node_class"]) &
                            (curves.knowledge == knowledge)].sort_values("round")
            if group.empty:
                continue
            n = selected.episodes[(selected.episodes.network_id == network) & (selected.episodes.knowledge == knowledge)].episode_uid.nunique()
            x = group["round"].to_numpy(dtype=float)
            ax.plot(x, (group.points_mean - 12) / denominator, color=colour, label=f"{label} · n = {n}")
            ax.fill_between(x, (group.points_mean_ci_low - 12) / denominator,
                            (group.points_mean_ci_high - 12) / denominator, color=colour, alpha=.14)
        ax.axvspan(6.5, 12.5, color="#E69F00", alpha=.08, label="rounds 7–12")
        ax.axvspan(12.5, 24.5, color="#009E73", alpha=.08, label="rounds 13–24")
        ax.set(title=network, xlabel="Round", ylabel="Power-use index (unitless)", xlim=(.5, 24.5))
        ax.legend(fontsize=7)
    return fig
