"""PNG charts for the solver benchmark. Matplotlib stays in the bench group."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

COLORS = {
    "stdlib": "#0f6e56",
    "stdlib --order": "#8d867c",
    "stdlib --assign": "#0f6e56",
    "pyvroom": "#1d4e89",
    "ortools": "#c44900",
}

SHORT = {
    "regiobus-per-zone": "regiobus",
    "opstapplaatsen": "opstap",
    "spreiding-gemengd": "spreiding",
}


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.size": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": False,
            "figure.facecolor": "#f7f5f2",
            "axes.facecolor": "#ffffff",
            "axes.edgecolor": "#d9d3c7",
            "text.color": "#1f2933",
            "axes.labelcolor": "#1f2933",
            "xtick.color": "#1f2933",
            "ytick.color": "#1f2933",
            "axes.titleweight": "bold",
        }
    )


def _lookup(rows: list[dict], scenarios: list[str], solvers: list[str], metric: str):
    found = []
    for solver in solvers:
        values = []
        for scenario in scenarios:
            match = next(
                row for row in rows if row["scenario"] == scenario and row["solver"] == solver
            )
            values.append(float(match[metric]))
        found.append((solver, values, COLORS[solver]))
    return found


def _grouped(ax, categories: list[str], series, ylabel: str, title: str) -> None:
    import numpy as np

    x = np.arange(len(categories))
    n = len(series)
    width = min(0.8 / n, 0.2)
    peak = 0.0
    for index, (name, values, color) in enumerate(series):
        offset = (index - (n - 1) / 2) * width
        ax.bar(
            x + offset,
            values,
            width * 0.9,
            label=name,
            color=color,
            zorder=3,
        )
        peak = max(peak, max(values, default=0.0))
    ax.set_xticks(x, categories)
    ax.set_ylabel(ylabel)
    ax.set_title(title, loc="left", fontsize=12, pad=8)
    ax.set_ylim(0, peak * 1.08 if peak else 1)
    ax.yaxis.grid(True, color="#e6e1d8", zorder=0)
    ax.set_axisbelow(True)


def _finish(fig, path: Path, solvers_for_legend, caption: str) -> None:
    handles, labels = [], []
    seen: set[str] = set()
    for ax in fig.axes:
        h, lab = ax.get_legend_handles_labels()
        for handle, label in zip(h, lab, strict=True):
            if label not in seen and label in solvers_for_legend:
                seen.add(label)
                handles.append(handle)
                labels.append(label)
    ordered = [label for label in solvers_for_legend if label in seen]
    handles = [handles[labels.index(label)] for label in ordered]
    fig.legend(
        handles,
        ordered,
        loc="outside lower center",
        ncol=min(4, len(ordered)),
        frameon=False,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        path,
        dpi=160,
        bbox_inches="tight",
        facecolor=fig.get_facecolor(),
        metadata={"Description": caption},
    )
    plt.close(fig)


def write_benchmark_charts(
    directory: Path,
    rows: list[dict],
    scenarios: list[str],
    subtitle: str,
) -> list[Path]:
    """Write the three comparison figures. Returns the paths."""
    _style()
    labels = [SHORT.get(name, name) for name in scenarios]
    order_rows = [row for row in rows if row["axis"] == "order"]
    assign_rows = [row for row in rows if row["axis"] == "assign"]
    order_solvers = ["stdlib", "pyvroom", "ortools"]
    assign_solvers = ["stdlib --order", "stdlib --assign", "pyvroom", "ortools"]
    written: list[Path] = []

    def figure(name: str, panels: list[tuple], solvers: list[str]) -> None:
        fig, axes = plt.subplots(2, 2, figsize=(11.2, 7.2), layout="constrained")
        fig.suptitle(name, fontsize=15, fontweight="bold", color="#1f2933")
        for ax, (title, ylabel, metric, source, solver_names) in zip(
            axes.ravel(), panels, strict=True
        ):
            _grouped(
                ax,
                labels,
                _lookup(source, scenarios, solver_names, metric),
                ylabel,
                title,
            )
        path = directory / _filename(name)
        _finish(fig, path, solvers, subtitle)
        written.append(path)

    order = [
        ("Langste rit", "minuten", "max_ride_min"),
        ("Gemiddelde rit", "minuten", "avg_ride_min"),
        ("Ritten langer dan 60 min", "leerlingen", "rides_over_60_min"),
        ("Kilometers (geschat)", "km", "total_km"),
    ]
    figure(
        "Volgorde per bus",
        [(*panel, order_rows, order_solvers) for panel in order],
        order_solvers,
    )
    figure(
        "Verdeling over de bussen",
        [
            ("Langste rit", "minuten", "max_ride_min", assign_rows, assign_solvers),
            ("Gemiddelde rit", "minuten", "avg_ride_min", assign_rows, assign_solvers),
            (
                "Ritten langer dan 60 min",
                "leerlingen",
                "rides_over_60_min",
                assign_rows,
                assign_solvers,
            ),
            (
                "Onevenwicht tussen bussen",
                "leerlingen (max − min)",
                "load_imbalance",
                assign_rows,
                assign_solvers,
            ),
        ],
        assign_solvers,
    )

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.8), layout="constrained")
    fig.suptitle("Rekentijd", fontsize=15, fontweight="bold", color="#1f2933")
    _grouped(
        axes[0],
        labels,
        _lookup(order_rows, scenarios, order_solvers, "seconds"),
        "seconden",
        "Volgorde per bus",
    )
    _grouped(
        axes[1],
        labels,
        _lookup(assign_rows, scenarios, assign_solvers, "seconds"),
        "seconden",
        "Verdeling over de bussen",
    )
    path = directory / "solver-bench-runtime.png"
    _finish(fig, path, order_solvers + assign_solvers, subtitle)
    written.append(path)
    return written


def _filename(title: str) -> str:
    if title.startswith("Volgorde"):
        return "solver-bench-order.png"
    return "solver-bench-assign.png"
