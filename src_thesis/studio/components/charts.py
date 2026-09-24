"""Plotly figure builders from service data (Series, MatrixTable, TopologyView)."""

import plotly.graph_objects as go

from src_thesis.application.models import MatrixTable, Series, TopologyView

from ..theme import SERIES


def _base(
    fig: go.Figure, height: int, y_title: str = "", x_title: str = ""
) -> go.Figure:
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


def line_figure(
    series: Series, height: int = 300, dashed: tuple[str, ...] = (), kind: str = "line"
) -> go.Figure:
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


def heatmap_figure(matrix: MatrixTable, height: int = 300) -> go.Figure:
    text = [
        [f"{m:.3f} ± {s:.3f}" if m is not None else "–" for m, s in zip(mr, sr)]
        for mr, sr in zip(matrix.mean, matrix.std)
    ]
    fig = go.Figure(
        go.Heatmap(
            z=matrix.mean,
            x=matrix.columns,
            y=matrix.rows,
            text=text,
            texttemplate="%{text}",
            colorscale=[[0, "#F0FDFA"], [1, "#0F766E"]],
            showscale=True,
            hovertemplate="%{y} · %{x}: %{text}<extra></extra>",
        )
    )
    fig = _base(fig, height)
    fig.update_layout(hovermode="closest")
    return fig


def topology_figure(
    topology: TopologyView,
    voltages: dict[str, float] | None = None,
    highlight: set[str] | None = None,
    height: int = 420,
) -> go.Figure:
    pos = {b["id"]: (b["x"], b["y"]) for b in topology.buses}
    xs, ys = [], []
    for line in topology.lines:
        (x0, y0), (x1, y1) = pos[line["from"]], pos[line["to"]]
        xs += [x0, x1, None]
        ys += [y0, y1, None]
    fig = go.Figure()
    fig.add_scatter(
        x=xs,
        y=ys,
        mode="lines",
        line=dict(color="rgba(100,116,139,0.55)", width=1.5),
        hoverinfo="skip",
        showlegend=False,
    )
    ids = [b["id"] for b in topology.buses]
    marker: dict = dict(
        size=[16 if b["kind"] == "external_grid" else 9 for b in topology.buses],
        line=dict(
            width=[3 if highlight and i in highlight else 0.5 for i in ids],
            color="#D97706",
        ),
    )
    if voltages:
        marker.update(
            color=[voltages.get(i, 1.0) for i in ids],
            colorscale="RdYlGn",
            cmin=0.93,
            cmax=1.05,
            colorbar=dict(title="V (pu)", thickness=12),
        )
    else:
        marker.update(
            color=[
                (
                    "#0F172A"
                    if b["kind"] == "external_grid"
                    else ("#D97706" if "pv" in b["kind"] else "#0F766E")
                )
                for b in topology.buses
            ]
        )
    fig.add_scatter(
        x=[pos[i][0] for i in ids],
        y=[pos[i][1] for i in ids],
        mode="markers",
        marker=marker,
        text=[
            f"{i} ({b['kind']})"
            + (f"<br>{voltages[i]:.3f} pu" if voltages and i in voltages else "")
            for i, b in zip(ids, topology.buses)
        ],
        hoverinfo="text",
        showlegend=False,
    )
    fig = _base(fig, height)
    fig.update_layout(hovermode="closest")
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, scaleanchor="x")
    return fig
