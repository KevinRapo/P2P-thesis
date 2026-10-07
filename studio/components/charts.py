"""Plotly figure builders from service data (Series, TopologyView)."""

import plotly.graph_objects as go

from services.models import Series, TopologyView

from studio.theme import SERIES


# --------------------------------------------------------------------------------------
# Line and bar charts
# --------------------------------------------------------------------------------------
def _base(
    fig: go.Figure, height: int, y_title: str = "", x_title: str = ""
) -> go.Figure:
    """Shared look of every chart: transparent background, font, grid lines, legend
    below.
    """
    fig.update_layout(
        height=height,
        margin=dict(l=48, r=16, t=12, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=12, color="#64748B"),
        legend=dict(orientation="h", y=-0.22, x=0),
        hovermode="x unified",
    )
    fig.update_xaxes(title=x_title, gridcolor="rgba(148,163,184,0.18)", zeroline=False)
    fig.update_yaxes(title=y_title, gridcolor="rgba(148,163,184,0.18)", zeroline=False)
    return fig


def styled(
    fig: go.Figure, height: int, y_title: str = "", x_title: str = ""
) -> go.Figure:
    """Give any figure the Studio's look (for figures built on a page)."""
    return _base(fig, height, y_title, x_title)


def line_figure(
    series: Series, height: int = 300, dashed: tuple[str, ...] = (), kind: str = "line"
) -> go.Figure:
    """Plotly figure of a ``Series``: one line (or bar group) per named y list.

    Args:
        series: The data.
        height: Height in pixels.
        dashed: Names drawn dashed, e.g. reference lines.
        kind: ``"line"`` or ``"bar"``.
    """
    fig = go.Figure()
    for i, (name, values) in enumerate(series.y.items()):
        color = SERIES[i % len(SERIES)]
        if kind == "bar":
            fig.add_bar(x=series.x, y=values, name=name, marker_color=color)
        else:
            fig.add_scatter(
                x=series.x,
                y=values,
                name=name,
                mode="lines",
                line=dict(
                    color=color, width=2, dash="dash" if name in dashed else "solid"
                ),
            )
    return _base(fig, height, series.y_label, series.x_label)


# --------------------------------------------------------------------------------------
# Network topology
# --------------------------------------------------------------------------------------
BUS_COLORS = {
    "external_grid": "#0F172A",
    "load": "#0F766E",
    "pv": "#D97706",
    "load+pv": "#EA580C",
    "gen": "#B45309",
    "storage": "#7C3AED",
    "bus": "#94A3B8",
}


def _bus_color(kind: str) -> str:
    """Marker colour for a bus kind; combined kinds fall back to their main element."""
    if kind in BUS_COLORS:
        return BUS_COLORS[kind]
    if "storage" in kind:
        return BUS_COLORS["storage"]
    return BUS_COLORS["load+pv"] if "pv" in kind else BUS_COLORS["load"]


def _branch_trace(fig: go.Figure, pos: dict, branches: list, **line) -> None:
    """Draw branches as one line trace (``None`` breaks the line between segments)."""
    xs, ys = [], []
    for br in branches:
        if br["from"] in pos and br["to"] in pos:
            (x0, y0), (x1, y1) = pos[br["from"]], pos[br["to"]]
            xs += [x0, x1, None]
            ys += [y0, y1, None]
    if xs:
        fig.add_scatter(
            x=xs, y=ys, mode="lines", line=line, hoverinfo="skip", showlegend=False
        )


def topology_figure(
    topology: TopologyView,
    voltages: dict[str, float] | None = None,
    highlight: set[str] | None = None,
    height: int = 420,
    violating: set[str] | None = None,
) -> go.Figure:
    """Network plot. Buses carry their ID as ``customdata`` for click handlers.

    Args:
        topology: Buses and branches.
        voltages: Voltage per bus; colours the buses on a fixed 0.93 to 1.05 pu scale.
        highlight: Buses outlined in amber (selected bus, participants).
        height: Height in pixels.
        violating: Buses outlined in red (outside their voltage limits).
    """
    pos = {b["id"]: (b["x"], b["y"]) for b in topology.buses}
    fig = go.Figure()
    lines = [br for br in topology.lines if br.get("kind", "line") == "line"]
    # Lines first (dotted when open), then transformers and switches drawn thick.
    _branch_trace(
        fig,
        pos,
        [br for br in lines if br.get("closed", True)],
        color="rgba(100,116,139,0.6)",
        width=1.5,
    )
    _branch_trace(
        fig,
        pos,
        [br for br in lines if not br.get("closed", True)],
        color="rgba(100,116,139,0.45)",
        width=1,
        dash="dot",
    )
    _branch_trace(
        fig,
        pos,
        [br for br in topology.lines if br.get("kind") in ("trafo", "switch")],
        color="#0F172A",
        width=3,
    )

    def hover(b: dict) -> str:
        """Hover text: bus ID, kind, voltage level and, after a preview, the voltage."""
        text = f"{b['id']}<br>{b['kind']}"
        if "vn_kv" in b:
            text += f" · {b['vn_kv']} kV"
        if voltages and b["id"] in voltages:
            text += f"<br>{voltages[b['id']]:.3f} pu"
        return text

    def size(b: dict) -> int:
        """Marker size: external grid large, buses with elements medium, empty buses
        small.
        """
        return 16 if b["kind"] == "external_grid" else (9 if b["kind"] != "bus" else 6)

    def outline(group: list[dict]) -> dict:
        """Amber outline for highlighted buses (selected bus, participants), red for
        buses outside their voltage limits."""
        bad = [bool(violating) and b["id"] in violating for b in group]
        marked = [bool(highlight) and b["id"] in highlight for b in group]
        return dict(
            width=[3 if m or v else 0.5 for m, v in zip(marked, bad)],
            color=["#DC2626" if v else "#D97706" for v in bad],
        )

    # After a preview: one trace coloured by voltage. Otherwise one trace per bus kind,
    # so the legend explains the colours.
    if voltages:
        group = topology.buses
        fig.add_scatter(
            x=[b["x"] for b in group],
            y=[b["y"] for b in group],
            mode="markers",
            customdata=[b["id"] for b in group],
            text=[hover(b) for b in group],
            hoverinfo="text",
            showlegend=False,
            marker=dict(
                size=[size(b) for b in group],
                color=[voltages.get(b["id"], 1.0) for b in group],
                colorscale="RdYlGn",
                cmin=0.93,
                cmax=1.05,
                colorbar=dict(title="V (pu)", thickness=12),
                line=outline(group),
            ),
        )
    else:
        kinds = sorted(
            {b["kind"] for b in topology.buses}, key=lambda k: k != "external_grid"
        )
        for kind in kinds:
            group = [b for b in topology.buses if b["kind"] == kind]
            fig.add_scatter(
                x=[b["x"] for b in group],
                y=[b["y"] for b in group],
                mode="markers",
                name=kind.replace("_", " "),
                customdata=[b["id"] for b in group],
                text=[hover(b) for b in group],
                hoverinfo="text",
                marker=dict(
                    size=[size(b) for b in group],
                    color=_bus_color(kind),
                    line=outline(group),
                ),
            )
    fig = _base(fig, height)
    fig.update_layout(hovermode="closest", legend=dict(orientation="h", y=-0.02))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, scaleanchor="x")
    return fig
