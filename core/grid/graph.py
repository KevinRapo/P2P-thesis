"""The paper's grid model on a SimBench network: line loading from the trades.

[P1] §3.5 models the grid as a graph whose edges carry the market's trades: each
executed trade adds its quantity to every edge on the shortest path between buyer
and seller (§3.5.3), and an edge's congestion is its flow over its capacity
(eq. 19). The total capacity is spread over the edges, more for shorter ones (the
original's ``GridNetwork.reset``).

Here the graph is the SimBench network's lines, and the paths are the market's own
(``SimBenchGrid.path`` and ``path_upstream``), so distances and zones are the same
as with the power flow. What differs is only the line loading the DSO's fees read:
``GraphGrid.assess`` gives it in the form of the power flow's
``GridAssessment.line_loading_percent``, so the fees (eq. 8) need no change.

Differences from the original, each recorded in the register: flows start from 0
every step instead of a random value that accumulates over the day (M-35); the
trades of all three stages count, not only stage 1 (M-36); trades with the DSO run
to the transformer (M-31). As in [P1], trades in opposite directions add up and
energy that is not traded is not seen.
"""

from __future__ import annotations

from typing import Mapping, Optional, Sequence

from core.grid.contract import GridAssessment, GridPath

CAPACITY_RULES = ("paper", "ratings")


class GraphGrid:
    """Line loading from the step's trades, over a capacity per line.

    Args:
        lines: Every line's length (km) and rating (kW), by line ID
            (``SimBenchGrid.line_table``).
        capacity: ``"paper"``: ``total_kw`` spread over the lines in inverse
            proportion to their length; ``"ratings"``: each line's own rating.
        total_kw: The total of ``"paper"``; ``None``: the sum of the ratings.
    """

    def __init__(
        self,
        lines: Mapping[str, tuple[float, float]],
        capacity: str = "paper",
        total_kw: Optional[float] = None,
    ) -> None:
        if capacity not in CAPACITY_RULES:
            raise ValueError(f"graph capacity must be one of {CAPACITY_RULES}")
        self.capacity_kw = capacities(lines, capacity, total_kw)

    def assess(
        self, step: int, flows: Sequence[tuple[GridPath, float]]
    ) -> GridAssessment:
        """The line loading of ``step``: every trade's power (kW) added to each line
        of its path, divided by the line's capacity. Voltages and losses are not
        modelled; their fields stay empty."""
        flow = {line: 0.0 for line in self.capacity_kw}
        for path, kw in flows:
            for line in path.lines:
                flow[line] += kw
        loading = {
            line: round(100.0 * f / self.capacity_kw[line], 2) if f else 0.0
            for line, f in flow.items()
        }
        return GridAssessment(
            step=step,
            converged=True,
            min_voltage_pu=None,
            max_voltage_pu=None,
            max_line_loading_percent=max(loading.values(), default=None),
            max_trafo_loading_percent=None,
            losses_kwh=None,
            external_grid_kwh=None,
            bus_voltage_pu={},
            violations=(),
            notes=("graph model: line loading from the trades ([P1] §3.5.3)",),
            line_loading_percent=loading,
        )


def capacities(
    lines: Mapping[str, tuple[float, float]],
    rule: str = "paper",
    total_kw: Optional[float] = None,
) -> dict[str, float]:
    """Each line's capacity (kW). ``"paper"``: C_e = C_tot · (1/ℓ_e) / Σ_k (1/ℓ_k),
    with C_tot = ``total_kw`` or the sum of the ratings; ``"ratings"``: the line's
    own rating. A line of zero length counts as 1 m."""
    if rule == "ratings":
        return {line: rating for line, (_, rating) in lines.items()}
    total = sum(r for _, r in lines.values()) if total_kw is None else total_kw
    inverse = {line: 1.0 / max(length, 1e-3) for line, (length, _) in lines.items()}
    norm = sum(inverse.values())
    return {line: total * w / norm for line, w in inverse.items()}
