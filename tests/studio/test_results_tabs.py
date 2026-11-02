"""Every Results tab draws, on runs with and without the step tables."""

import asyncio
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from nicegui.testing import user_simulation

from core.grid.contract import BranchView, BusView, TopologyView
from core.runner import results
from studio.adapters.results_service import ResultsService
from studio.pages.results import validation
from studio.pages.results.common import DayChart, Selection
from studio.pages.results.grid import GridTab
from studio.pages.results.learning import LearningTab
from studio.pages.results.market import MarketTab
from studio.pages.results.steps import StepView
from studio.pages.results.validation import ValidationTab
from tests.runner.test_results import make_run, where  # noqa: F401 (the fixture)

TABS = (ValidationTab, LearningTab, MarketTab, GridTab)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize("tab", TABS)
async def test_a_tab_draws_a_run_from_before_the_step_tables(tab, where):  # noqa: F811
    service = ResultsService(where)
    keys = ["local/grid/ppo_dtde_s0", "local/grid/ppo_dtde_s1"]
    built = []

    async def root() -> None:
        shown = tab(service, Selection(open=lambda label: None))
        shown.build(keys, shown.read(keys))
        built.append(shown)

    async with user_simulation(root) as user:
        await user.open("/")
        assert built


def overview_table() -> pd.DataFrame:
    rows = []

    for key, seed, reward, money in (
        ("a", 0, "bill", 1.0),
        ("b", 1, "bill", 3.0),
        ("c", 2, "bill", 5.0),
        ("d", 0, "salazar", -9.0),
    ):
        for indicator in validation.HEADLINES:
            for policy, value in (("trained", money), ("zero", -5.0)):
                rows.append(
                    {
                        "key": key,
                        "seed": seed,
                        "policy": policy,
                        "day": "d1",
                        "indicator": indicator,
                        "value": value,
                        "experiment": "x",
                        "variant": reward,
                        "paradigm": "ctde",
                        "reward": reward,
                        "observation": "paper",
                        "prices": "p",
                        "peer_charge": 0.0,
                        "network": "n",
                        "grid_method": "ac",
                        "test_days": "d",
                    }
                )

    return pd.DataFrame(rows)


def test_a_row_stands_for_what_differs():
    assert validation.row_columns(overview_table()) == ["reward"]
    assert validation.row_columns(
        overview_table().assign(reward="bill", variant="v")
    ) == ["key"]


def test_a_cell_shows_the_mean_with_its_seeds_or_interval():
    assert validation.number(pd.Series({"mean": 1.0, "values": [1.0]})) == "1.0"
    both = pd.Series({"mean": 1.5, "values": [1.0, 2.0]})
    assert validation.number(both) == "1.5 (1.0, 2.0)"
    interval = pd.Series({"mean": 1.5, "low": 1.0, "high": 2.0})
    assert validation.number(interval) == "1.5 [1.0, 2.0]"


@pytest.mark.anyio
async def test_a_row_opens_on_its_median_seed():
    opened = []
    tab = SimpleNamespace(selection=Selection(open=opened.append))
    views = []

    async def root() -> None:
        views.append(validation.Overview(overview_table(), tab))

    async with user_simulation(root) as user:
        await user.open("/")
        view = views[0]
        assert view.closer.options == ["bill", "salazar"]
        view.closer.value = "bill"
        view.open("Market")
        assert opened == ["Market"] and tab.selection.run == "b"
        view.reference.value = "bill"
        view.view.value = "zero"


@pytest.mark.anyio
@pytest.mark.parametrize("tab", TABS)
async def test_a_live_refresh_reaches_the_charts(tab, where):  # noqa: F811
    service = ResultsService(where)
    keys = ["local/grid/ppo_dtde_s0", "local/grid/ppo_dtde_s1"]
    done = []

    async def root() -> None:
        shown = tab(service, Selection(open=lambda label: None))
        shown.build(keys, shown.read(keys))
        shown.update(shown.read(keys))
        done.append(True)

    async with user_simulation(root) as user:
        await user.open("/")
        assert done


def test_a_missing_value_is_no_point_on_the_chart():
    table = pd.DataFrame(
        {
            "metric": ["m", "m"],
            "policy": ["trained"] * 2,
            "day": ["d1", "d2"],
            "value": [1.0, float("nan")],
            "key": ["a", "a"],
        }
    )
    chart = DayChart(
        table=table, metric="m", by="key", policy="trained", band=False, labels={}
    )
    assert np.isnan(list(chart.figure().data[0].y)[1])


@pytest.mark.anyio
async def test_one_row_has_nothing_to_differ_from():
    table = overview_table()
    tab = SimpleNamespace(selection=Selection(open=lambda label: None))
    views = []

    async def root() -> None:
        views.append(validation.Overview(table[table.key == "a"], tab))

    async with user_simulation(root) as user:
        await user.open("/")
        view = views[0]
        view.reference.set_options({"": "Nothing", "a": "a"}, value="a")
        view.draw()
        await user.should_see("Nothing to compare it with.")


PEOPLE = [
    {"id": "P1", "owns": ["Load 1", "SGen 1"], "battery": None},
    {"id": "P2", "owns": ["Load 2", "SGen 2"], "battery": {"capacity": 5}},
    {"id": "P3", "owns": ["Load 3"], "battery": None},
]


def run_with(people, bills: dict[str, tuple[float, float]]):
    """A run's reader with a scenario of ``people``; ``bills``: per agent, its bill
    under the trained policy and under zero."""
    table = pd.DataFrame(
        {
            "policy": ["trained", "zero"] * len(bills) * 2,
            "day": [d for d in ("d1", "d2") for _ in range(2 * len(bills))],
            "agent": [a for a in bills for _ in range(2)] * 2,
            "bill": [b for one in bills.values() for b in one] * 2,
        }
    )

    return SimpleNamespace(
        key="k",
        settings={"scenario": people},
        table=lambda name: table if name == "heldout_agents" else None,
    )


def test_participants_are_grouped_by_what_they_own():
    result = run_with({"participants": PEOPLE}, {})
    assert results.participant_groups(result) == {
        "P1": "PV",
        "P2": "battery",
        "P3": "other",
    }
    assert results.participant_groups(run_with("scenario.json", {})) == {}


def test_a_participant_gains_its_bill_over_zero():
    bills = {"P1": (-1.0, -4.0), "P2": (-3.0, -2.0)}
    found = results.participant_gains([run_with({"participants": PEOPLE}, bills)])
    assert list(found.key) == ["k", "k"]
    assert list(found.agent) == ["P1", "P2"]
    assert list(found.group) == ["PV", "battery"]
    assert list(found.gain) == [3.0, -1.0]
    other = results.participant_gains([run_with("scenario.json", bills)])
    assert list(other.group) == [results.UNKNOWN_GROUP] * 2
    assert results.participant_gains([]).empty


@pytest.mark.anyio
async def test_quick_changes_leave_one_set_of_charts(tmp_path):
    steps = pd.DataFrame(
        {
            "policy": ["trained"] * 4,
            "day": ["d1", "d1", "d2", "d2"],
            "step": [0, 1, 0, 1],
            "p2p_kwh": [1.0, 2.0, 3.0, 4.0],
        }
    )

    class Tables:
        def table(self, key, name):
            return steps if name == "heldout_steps" else None

    views = []
    selection = Selection(open=lambda label: None)

    async def root() -> None:
        views.append(StepView(Tables(), {"a": "a"}, selection, [("kWh", ["p2p_kwh"])]))

    async with user_simulation(root) as user:
        await user.open("/")
        view = views[0]
        await asyncio.gather(view.draw(), view.draw(), view.draw())
        await asyncio.sleep(0.1)
        assert len(view.box.default_slot.children) == 1


# --------------------------------------------------------------------------------------
# The plots chosen from the gallery
# --------------------------------------------------------------------------------------
def small_network() -> TopologyView:
    buses = tuple(BusView(b, 0.0 + i, 0.0, "load", 0.4) for i, b in enumerate("ABC"))
    lines = (BranchView("L1", "A", "B", "line"), BranchView("L2", "B", "C", "line"))
    return TopologyView(buses, lines, "A")


def trade_rows() -> pd.DataFrame:
    rows = [
        ("trained", "d1", 0, "P2", "P1", 0.2, 2.0, 1),
        ("trained", "d1", 0, "P3", "P1", 0.3, 1.0, 2),
        ("trained", "d2", 1, "P1", "P10", 0.25, 4.0, 2),
        ("trained", "d2", 1, "DSO", "P1", 0.4, 5.0, 3),
        ("zero", "d1", 0, "P2", "P3", 0.2, 9.0, 2),
    ]
    frame = pd.DataFrame(
        rows,
        columns=["policy", "day", "step", "seller", "buyer", "price", "kwh", "stage"],
    )
    return frame.assign(key="k", band=0.5)


def test_the_matrix_sums_the_peer_trades_of_a_policy():
    from studio.pages.results.trades import trade_matrix

    kwh = trade_matrix(trade_rows(), "trained", "kwh")
    assert list(kwh.index) == ["P1", "P2", "P3", "P10"]  # P2 before P10
    assert kwh.loc["P1", "P2"] == 2.0 and kwh.loc["P10", "P1"] == 4.0
    assert np.isnan(kwh.loc["P2", "P3"])  # the zero policy's, and no trade
    assert trade_matrix(trade_rows(), "trained", "money").loc["P1", "P3"] == 0.3
    assert trade_matrix(trade_rows(), "trained", "count").loc["P1", "P2"] == 1


def test_a_box_per_run_or_version_of_the_peer_trades():
    from studio.pages.results.trades import TradeBoxChart

    trades = trade_rows().assign(variant="v")
    chart = TradeBoxChart(
        trades=trades, labels={"k": "run"}, metric="kwh", by="variant", policy="trained"
    )
    boxes = chart.figure().data
    assert [b.name for b in boxes] == ["v"]
    assert sorted(boxes[0].y) == [1.0, 2.0, 4.0]  # peers only, one policy
    empty = TradeBoxChart(
        trades=pd.DataFrame(), labels={}, metric="kwh", by="key", policy="all"
    )
    assert not empty.figure().data


def test_the_network_colours_its_lines_and_links_its_trades():
    from studio.components.charts import NetworkChart

    class Linked(NetworkChart):
        def draw(self) -> None:
            self.trade_links(
                [("P1", "P2", 1.0, 0.2, 2), ("DSO", "P2", 1.0, 0.4, 3)],
                {"P1": "B", "P2": "C"},
            )

    chart = Linked(topology=small_network(), loading={"L1": 90.0, "L2": float("nan")})
    names = [t.name for t in chart.figure().data]
    assert "Peer trade" in names and "DSO trade" in names
    assert len([t for t in chart.fig.data if t.text in ("L1: 90 %", "L2")]) == 2
    plain = NetworkChart(topology=small_network())
    assert not any(t.text == "L2" for t in plain.figure().data)


def test_a_step_view_row_is_the_mean_over_the_days():
    from studio.pages.results.steps import mean_over_days, with_peer_share

    steps = pd.DataFrame(
        {
            "policy": ["trained"] * 4,
            "day": ["d1", "d1", "d2", "d2"],
            "step": [0, 1, 0, 1],
            "p2p_kwh": [1.0, 0.0, 3.0, 0.0],
            "sold_to_dso_kwh": [1.0, 0.0, 0.0, 0.0],
            "bought_from_dso_kwh": [0.0, 0.0, 1.0, 0.0],
        }
    )
    shared = with_peer_share(steps)
    assert list(shared.peer_share.round(2).fillna(-1)) == [0.5, -1, 0.75, -1]
    mean = mean_over_days(shared)
    assert list(mean.step) == [0, 1] and mean.peer_share[0] == pytest.approx(0.625)
    assert with_peer_share(None) is None
    assert "peer_share" not in with_peer_share(steps.drop(columns="p2p_kwh"))


@pytest.mark.anyio
async def test_the_day_selector_offers_the_mean_over_the_days():
    steps = pd.DataFrame(
        {
            "policy": ["trained"] * 4,
            "day": ["d1", "d1", "d2", "d2"],
            "step": [0, 1, 0, 1],
            "p2p_kwh": [1.0, 2.0, 3.0, 4.0],
        }
    )

    class Tables:
        def table(self, key, name):
            return steps if name == "heldout_steps" else None

    views, selection = [], Selection(open=lambda label: None)

    async def root() -> None:
        views.append(StepView(Tables(), {"a": "a"}, selection, [("kWh", ["p2p_kwh"])]))

    async with user_simulation(root) as user:
        await user.open("/")
        view = views[0]
        await view.draw()
        assert list(view.day.options)[0] == "all" and view.day.value == "d1"
        view.day.value = "all"
        await asyncio.sleep(0.1)
        assert selection.day == "d1"  # the mean is no day to share
        assert len(view.box.default_slot.children) == 1


def test_a_version_pools_its_seeds_on_the_return_curve():
    from studio.pages.results.learning import CurveChart

    rows = [
        (key, seed, step, value)
        for key, seed, values in (("a0", 0, (1.0, 2.0)), ("a1", 1, (3.0, 6.0)))
        for step, value in zip((0, 100), values)
    ]
    curves = pd.DataFrame(rows, columns=["key", "seed", "env_steps", "v"])
    curves = curves.assign(
        policy="trained", target="t", experiment="e", paradigm="ctde", variant=None
    ).rename(columns={"v": "team_return_mean"})
    labels = {"a0": "run 0", "a1": "run 1"}
    kept = dict(
        curves=curves,
        training=pd.DataFrame(),
        labels=labels,
        value="team_return_mean",
        train=False,
    )
    own = CurveChart(**kept)
    assert [t.name for t in own.figure().data if t.name] == ["run 0", "run 1"]
    pooled = CurveChart(**kept, by="version")
    line = [t for t in pooled.figure().data if t.name][0]
    assert line.name == "t/e/ctde/ (2 seeds)" and list(line.y) == [2.0, 4.0]
    band = [t for t in pooled.fig.data if t.fill == "toself"][0]
    assert max(band.y) == 6.0 and min(band.y) == 1.0


@pytest.mark.anyio
async def test_the_replay_steps_through_a_day(monkeypatch):
    from studio.pages.results import replay

    grid = pd.DataFrame(
        {
            "policy": "trained",
            "day": "d1",
            "step": [0, 1, 2],
            "bus_voltage/B": [1.0, 0.99, 0.98],
            "line_loading/L1": [10.0, 50.0, 90.0],
        }
    )
    trades = trade_rows().query("policy == 'trained' and day == 'd1'")

    class Tables:
        def table(self, key, name):
            return {"heldout_grid": grid, "heldout_trades": trades}.get(name)

        def network(self, key):
            return "code", {"P1": "B", "P2": "C"}

    topology = small_network()
    fake = SimpleNamespace(grid=SimpleNamespace(topology=lambda ref: topology))
    monkeypatch.setattr(replay, "services", lambda: fake)
    views, selection = [], Selection(open=lambda label: None)

    async def root() -> None:
        views.append(replay.Replay(Tables(), {"k": "k"}, selection))

    async with user_simulation(root) as user:
        await user.open("/")
        view = views[0]
        await asyncio.sleep(0.3)  # the draw the page starts itself
        assert view.day.value == "d1" and selection.day == "d1"
        names = [t.name for t in view.chart.figure().data]
        assert "Peer trade" in names  # step 0 has peer trades
        view.step.value = 2
        assert view.chart.o.loading["L1"] == 90.0 and view.chart.o.trades == []
        view._toggle()
        assert view.clock.active
        view._advance()
        view._stop()
        assert not view.clock.active


@pytest.mark.anyio
async def test_the_replay_of_an_old_run_is_a_caption():
    from studio.pages.results import replay

    class Tables:
        def table(self, key, name):
            return None

        def network(self, key):
            return None, {}

    views = []

    async def root() -> None:
        views.append(replay.Replay(Tables(), {"k": "k"}, Selection(open=print)))

    async with user_simulation(root) as user:
        await user.open("/")
        await views[0].draw()
        await user.should_see("Not recorded")
