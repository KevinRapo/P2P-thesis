"""The two grid methods (``grid.method``): the power flow and the paper's graph model.

The graph model (``core/grid/graph.py``) gives the DSO's fees a line loading built
from the step's trades; the power flow still runs and is recorded. These tests
check the graph model's capacity and flows, that a graph-mode step charges its fees
from the graph loading while ``record.grid`` stays the power flow, that the two
arms give the same physics for a policy that ignores fees, and the measured
voltage drop.

Run with ``python -m pytest tests/market/test_grid_methods.py -q`` in the
``marlem`` conda env. The first market reset loads the SimBench network (~10 s).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.env import MarketEnv, net_position_policy
from core.grid.contract import GridAssessment, GridPath
from core.grid.graph import GraphGrid, capacities
from core.market.dso.dso import Dso

SCENARIO = Path(__file__).resolve().parents[2] / "scenarios/validate_market.json"
DAY = "2016-07-01"
LINES = {"a": (0.1, 100.0), "b": (0.2, 50.0), "c": (0.4, 200.0)}


# --------------------------------------------------------------------------------------
# The graph model alone
# --------------------------------------------------------------------------------------
def test_paper_capacity_is_the_total_spread_by_inverse_length():
    cap = capacities(LINES, "paper")
    assert sum(cap.values()) == pytest.approx(350.0)  # the sum of the ratings
    assert cap["a"] == pytest.approx(2 * cap["b"]) == pytest.approx(4 * cap["c"])
    assert sum(capacities(LINES, "paper", 1000.0).values()) == pytest.approx(1000.0)


def test_ratings_capacity_is_each_lines_own():
    assert capacities(LINES, "ratings") == {"a": 100.0, "b": 50.0, "c": 200.0}


def test_flows_of_trades_add_up_on_shared_lines():
    graph = GraphGrid(LINES, "ratings")
    one = GridPath(lines=("a", "b"))
    two = GridPath(lines=("b",))
    found = graph.assess(3, [(one, 10.0), (two, 5.0)])
    assert found.line_loading_percent == {"a": 10.0, "b": 30.0, "c": 0.0}
    assert found.max_line_loading_percent == 30.0
    assert found.converged and found.bus_voltage_pu == {}


def test_unknown_capacity_rule_is_refused():
    with pytest.raises(ValueError):
        GraphGrid(LINES, "length")


# --------------------------------------------------------------------------------------
# The measured voltage drop
# --------------------------------------------------------------------------------------
def test_measured_voltage_drop_is_the_difference_at_the_paths_ends():
    dso = Dso(0.08, 0.30, voltage_drop="measured")
    grid = GridAssessment(
        step=0, converged=True, min_voltage_pu=1.0, max_voltage_pu=1.03,
        max_line_loading_percent=0.0, max_trafo_loading_percent=None,
        losses_kwh=0.0, external_grid_kwh=0.0,
        bus_voltage_pu={"x": 1.03, "y": 1.01}, violations=(),
    )
    dso.observe(grid)
    path = GridPath(distance_km=0.2, bus_a="x", bus_b="y")
    assert dso.voltage_drop_of(path) == pytest.approx(0.02)
    fees = dso.fees_of(quantity=2.0, price=0.2, path=path, loss_kwh=0.0)
    assert fees.voltage == pytest.approx(0.02 * 2.0 * 0.2)
    distance = Dso(0.08, 0.30)
    assert distance.voltage_drop_of(path) == pytest.approx(0.15 * 0.2)


# --------------------------------------------------------------------------------------
# The market with each method
# --------------------------------------------------------------------------------------
def play(method: str, **grid) -> list:
    """One day with the net-position baseline; the step records."""
    env = MarketEnv(
        {
            "scenario": str(SCENARIO),
            "days": [DAY],
            "grid": {"method": method, **grid},
        }
    )
    policy = net_position_policy(env)
    obs, _ = env.reset(options={"day": DAY})
    records = []
    while True:
        obs, _, terminated, _, _ = env.step(policy(obs))
        records.append(env.last_record)
        if terminated["__all__"]:
            return records


@pytest.fixture(scope="module")
def arms() -> dict:
    return {"powerflow": play("powerflow"), "graph": play("graph")}


def test_graph_mode_charges_fees_from_the_graph_loading(arms):
    dso = Dso(0.08, 0.30)
    for record in arms["graph"]:
        assert record.signal is not None and record.grid.bus_voltage_pu
        for trade in record.trades:
            if trade.quantity <= 0:
                continue
            c = min(
                1.0,
                max(
                    (record.signal.line_loading_percent[line] for line in _lines(trade)),
                    default=0.0,
                )
                / 100,
            )
            thermal = 0.0
            if c > dso.thermal_threshold:
                f = (c - dso.thermal_threshold) / (1 - dso.thermal_threshold)
                thermal = min(f, dso.thermal_cap) * trade.quantity * trade.price
            assert trade.fee_parts.thermal == pytest.approx(thermal)


def test_powerflow_mode_has_no_signal(arms):
    assert all(r.signal is None for r in arms["powerflow"])


def test_the_same_physics_when_the_policy_ignores_fees(arms):
    for a, b in zip(arms["powerflow"], arms["graph"]):
        assert a.grid.line_loading_percent == b.grid.line_loading_percent
        assert a.grid.bus_voltage_pu == b.grid.bus_voltage_pu


def test_the_graph_loading_differs_from_the_measured_one(arms):
    graph = max(r.signal.max_line_loading_percent for r in arms["graph"])
    measured = max(r.grid.max_line_loading_percent for r in arms["graph"])
    assert graph != pytest.approx(measured)


_PATHS: dict = {}


def _lines(trade) -> tuple[str, ...]:
    """The lines the fee of ``trade`` used, from a market of the graph arm."""
    if not _PATHS:
        env = MarketEnv(
            {"scenario": str(SCENARIO), "days": [DAY], "grid": {"method": "graph"}}
        )
        env.reset(options={"day": DAY})
        _PATHS["market"] = env.market
    market = _PATHS["market"]
    dso = market.dso.id
    if dso in (trade.buyer_id, trade.seller_id):
        other = trade.seller_id if trade.buyer_id == dso else trade.buyer_id
        return market._upstream(other).lines
    return market._path(trade.buyer_id, trade.seller_id).lines
