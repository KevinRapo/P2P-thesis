"""The run table (``studio/components/run_table.py``) in NiceGUI's user simulation:
filters (one or more experiments, text) choose what is shown, ticking is separate,
a tick survives a filter, and ticks and filters come back on the next visit."""

from __future__ import annotations

import json

import pytest
from nicegui.testing.user_simulation import user_simulation

from studio.adapters.results_service import ResultsService
from studio.components import run_table
from studio.components.run_table import RunTable


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _runs(root, experiment: str, names: list[str]) -> None:
    for name in names:
        folder = root / experiment / name
        folder.mkdir(parents=True)
        (folder / "run.json").write_text(
            json.dumps({"algorithm": "ppo", "paradigm": "ctde", "seed": 0}),
            encoding="utf-8",
        )


@pytest.mark.anyio
async def test_showing_and_ticking_are_separate(tmp_path):
    _runs(tmp_path, "probes_fast", ["ppo_ctde_p1_s0", "ppo_dtde_p1_s0"])
    _runs(tmp_path, "probes_fast_SM", ["ppo_ctde_p9_s0", "ppo_dtde_p9_s0"])
    found: dict = {}
    changes: list = []

    def root() -> None:
        async def changed() -> None:
            changes.append(list(found["table"].selected))

        found["table"] = RunTable(
            ResultsService({"local": tmp_path}), changed, "test_one"
        )

    async with user_simulation(root) as user:
        await user.open("/")
        table: RunTable = found["table"]
        await table.load()
        shown = lambda: sorted(r["key"] for r in table.runs.rows)  # noqa: E731
        assert len(shown()) == 4 and table.selected == []

        # An experiment shows its runs and ticks none of them.
        table.experiment.set_value(["local/probes_fast_SM"])
        assert shown() == [
            "local/probes_fast_SM/ppo_ctde_p9_s0",
            "local/probes_fast_SM/ppo_dtde_p9_s0",
        ]
        assert table.selected == []

        # One run ticked by its box.
        table.runs.selected = [table.runs.rows[0]]
        await table._selected()
        assert table.selected == ["local/probes_fast_SM/ppo_ctde_p9_s0"]

        # Another experiment: the tick stays, hidden; untick all keeps the filter.
        table.experiment.set_value(["local/probes_fast"])
        assert table.selected == ["local/probes_fast_SM/ppo_ctde_p9_s0"]
        await table.tick_shown()
        assert len(table.selected) == 3
        await table.untick_all()
        assert table.selected == [] and table.experiment.value == ["local/probes_fast"]
        assert len(shown()) == 2

        # Two experiments at once, with one run of each ticked.
        table.experiment.set_value(["local/probes_fast", "local/probes_fast_SM"])
        assert len(shown()) == 4
        table.runs.selected = [
            r for r in table.runs.rows if r["key"].endswith("ppo_ctde_p9_s0")
        ] + [r for r in table.runs.rows if r["key"].endswith("ppo_dtde_p1_s0")]
        await table._selected()
        assert sorted(table.selected) == [
            "local/probes_fast/ppo_dtde_p1_s0",
            "local/probes_fast_SM/ppo_ctde_p9_s0",
        ]
        await table.untick_all()

        # The text filter narrows what is shown, and Tick shown ticks only that.
        table.experiment.set_value(None)
        table.search.set_value("dtde")
        assert len(shown()) == 2
        await table.tick_shown()
        assert all("dtde" in k for k in table.selected) and len(table.selected) == 2
        assert changes  # the page was told every time


@pytest.mark.anyio
async def test_targets_and_folders_narrow_the_experiments_offered(tmp_path):
    local, cluster = tmp_path / "local", tmp_path / "cluster"
    _runs(local, "plain", ["ppo_ctde_s0"])
    _runs(cluster, "plain", ["ppo_ctde_s0"])
    _runs(cluster, "test/one", ["ppo_ctde_s0"])
    _runs(cluster, "final/two", ["ppo_ctde_s0", "ppo_dtde_s0"])
    _runs(cluster, "deep/er/three", ["ppo_ctde_s0"])
    found: dict = {}

    async def changed() -> None:
        pass

    def root() -> None:
        found["table"] = RunTable(
            ResultsService({"local": local, "cluster": cluster}),
            changed,
            "test_two",
        )

    async with user_simulation(root) as user:
        await user.open("/")
        table: RunTable = found["table"]
        await table.load()
        shown = lambda: sorted(r["key"] for r in table.runs.rows)  # noqa: E731
        assert len(shown()) == 6 and table.target.options == ["cluster", "local"]
        assert table.folder.options == {
            "": "(top level)",
            "deep": "deep",
            "deep/er": "deep/er",
            "final": "final",
            "test": "test",
        }

        # A target narrows the folders and the experiments offered.
        table.target.set_value(["local"])
        assert shown() == ["local/plain/ppo_ctde_s0"]
        assert list(table.folder.options) == [""]
        assert table.experiment.options == ["local/plain"]

        # A folder inside the target narrows them further.
        table.target.set_value(["cluster"])
        table.folder.set_value(["final"])
        assert table.experiment.options == ["cluster/final/two"]
        assert len(shown()) == 2

        # A folder includes those under it; the lower one narrows further.
        table.folder.set_value(["deep"])
        assert shown() == ["cluster/deep/er/three/ppo_ctde_s0"]
        table.folder.set_value(["deep/er"])
        assert shown() == ["cluster/deep/er/three/ppo_ctde_s0"]

        # The top level: the experiments in no folder.
        table.folder.set_value([""])
        assert shown() == ["cluster/plain/ppo_ctde_s0"]

        # A choice the narrower selection no longer offers is dropped, not stuck.
        table.experiment.set_value(["cluster/plain"])
        table.folder.set_value(["test"])
        assert table.experiment.value == []
        assert shown() == ["cluster/test/one/ppo_ctde_s0"]


@pytest.mark.anyio
async def test_the_ticks_and_filters_come_back_on_the_next_visit(tmp_path):
    _runs(tmp_path, "one", ["ppo_ctde_s0", "ppo_dtde_s0"])
    _runs(tmp_path, "two", ["ppo_ctde_s0"])
    tables: list = []

    async def changed() -> None:
        pass

    def root() -> None:
        tables.append(RunTable(ResultsService({"local": tmp_path}), changed, "visit"))

    async with user_simulation(root) as user:
        await user.open("/")
        await tables[-1].load()
        tables[-1].experiment.set_value(["local/one"])
        tables[-1].search.set_value("dtde")
        await tables[-1].tick_shown()
        tables[-1].only_ticked.set_value(True)

        # Back on the page: nothing is there until the runs are read, and nothing
        # kept is lost before that.
        await user.open("/")
        table: RunTable = tables[-1]
        assert len(tables) == 2 and table.selected == []
        await table.load()
        assert table.selected == ["local/one/ppo_dtde_s0"]
        assert table.experiment.value == ["local/one"]
        assert table.search.value == "dtde" and table.only_ticked.value is True
        assert [r["key"] for r in table.runs.rows] == ["local/one/ppo_dtde_s0"]
        assert [r["key"] for r in table.runs.selected] == ["local/one/ppo_dtde_s0"]

        # A later read brings nothing back over what was changed since.
        await table.untick_all()
        await table.load()
        assert table.selected == []


@pytest.mark.anyio
async def test_what_is_gone_is_dropped_from_what_came_back(tmp_path):
    local, other = tmp_path / "local", tmp_path / "other"
    _runs(local, "one", ["ppo_ctde_s0", "ppo_dtde_s0"])
    tables: list = []
    where = {"local": local}

    async def changed() -> None:
        pass

    def root() -> None:
        tables.append(RunTable(ResultsService(where), changed, "gone"))

    async with user_simulation(root) as user:
        await user.open("/")
        await tables[-1].load()
        tables[-1].experiment.set_value(["local/one"])
        await tables[-1].tick_shown()

        # The experiment left this target: the page comes up empty of it, unbroken.
        _runs(other, "two", ["ppo_ctde_s0"])
        where["local"] = other
        await user.open("/")
        table: RunTable = tables[-1]
        await table.load()
        assert table.selected == [] and table.experiment.value == []
        assert [r["key"] for r in table.runs.rows] == ["local/two/ppo_ctde_s0"]


@pytest.mark.anyio
async def test_an_empty_read_loses_no_ticks(tmp_path):
    _runs(tmp_path, "one", ["ppo_ctde_s0"])
    tables: list = []
    where = {"local": tmp_path}

    async def changed() -> None:
        pass

    def root() -> None:
        tables.append(RunTable(ResultsService(where), changed, "empty"))

    async with user_simulation(root) as user:
        await user.open("/")
        await tables[-1].load()
        await tables[-1].tick_shown()

        where["local"] = tmp_path / "nothing_here"  # a mirror not there for a moment
        await user.open("/")
        await tables[-1].load()
        assert tables[-1].selected == []

        where["local"] = tmp_path
        await user.open("/")
        await tables[-1].load()
        assert tables[-1].selected == ["local/one/ppo_ctde_s0"]


@pytest.mark.anyio
async def test_a_page_left_during_the_read_loses_nothing(tmp_path, monkeypatch):
    _runs(tmp_path, "one", ["ppo_ctde_s0"])
    tables: list = []

    async def changed() -> None:
        pass

    async def left(*_) -> None:  # NiceGUI's answer when the page has closed
        return None

    def root() -> None:
        tables.append(RunTable(ResultsService({"local": tmp_path}), changed, "left"))

    async with user_simulation(root) as user:
        await user.open("/")
        await tables[-1].load()
        await tables[-1].tick_shown()

        await user.open("/")
        with monkeypatch.context() as patch:
            patch.setattr(run_table.run, "io_bound", left)
            await tables[-1].load()

        assert tables[-1].overview.empty and tables[-1].selected == []

        await user.open("/")
        await tables[-1].load()
        assert tables[-1].selected == ["local/one/ppo_ctde_s0"]
