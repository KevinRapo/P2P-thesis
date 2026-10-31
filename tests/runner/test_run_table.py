"""The run table (``studio/components/run_table.py``) in NiceGUI's user simulation:
filters (one or more experiments, text) choose what is shown, ticking is separate,
and a tick survives a filter."""

from __future__ import annotations

import json

import pytest
from nicegui.testing.user_simulation import user_simulation

from studio.adapters.results_service import ResultsService
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
            ResultsService({"local": tmp_path}), changed, "test_show_tests"
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
            "test_show_tests",
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
