"""Every Results tab draws, on runs with and without the step tables."""

import asyncio
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from nicegui.testing import user_simulation

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
