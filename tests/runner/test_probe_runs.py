"""What each RL probe is and what a probe run scored (``probe_runs.py``), and how the
Studio's ValidationService passes it on: hand-written run folders, no training."""

from __future__ import annotations

import json
import subprocess
import sys

import pandas as pd

from core.runner import probe_runs
from core.rl.scripts.probe_check import PROBES
from studio.adapters.results_service import ResultsService
from studio.adapters.validation_service import ValidationService


def test_every_probe_is_described_under_its_own_name():
    assert set(probe_runs.ABOUT) == set(PROBES)
    assert all(probe_runs.ABOUT[k].name == p.name for k, p in PROBES.items())


def test_the_studio_reads_it_without_loading_ray():
    code = (
        "import sys; import core.runner.probe_runs; "
        "import studio.adapters.validation_service; print('ray' in sys.modules)"
    )
    found = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert found.stdout.strip() == "False"


def _probe_run(folder, scored: bool = True):
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(
        json.dumps({"algorithm": "ppo", "paradigm": "ctde", "seed": 1}),
        encoding="utf-8",
    )

    if scored:
        pd.DataFrame(
            [{"probe": "8a", "paradigm": "ctde", "result": "FAIL", "worst": 2.5}]
        ).to_csv(folder / "score.csv", index=False)
        pd.DataFrame(
            [
                {
                    "state": "obs 0",
                    "output": "action agent_1 side",
                    "expected": 0.0,
                    "got": 1.0,
                    "tolerance": 0.0,
                    "error": 1.0,
                    "ok": False,
                }
            ]
        ).to_csv(folder / "checks.csv", index=False)


def test_a_probe_run_is_read_from_its_name_and_files(tmp_path):
    _probe_run(tmp_path / "ppo_ctde_p8a_s1_x2")
    info = probe_runs.read_probe_run(tmp_path / "ppo_ctde_p8a_s1_x2")
    assert (info.probe, info.paradigm, info.seed, info.scale) == ("8a", "ctde", 1, 2)
    assert (info.result, info.worst) == ("FAIL", 2.5)
    assert len(info.checks) == 1 and info.about.name == "Mutual choice, coordination"
    _probe_run(tmp_path / "ppo_dtde_p3_s0", scored=False)
    unscored = probe_runs.read_probe_run(tmp_path / "ppo_dtde_p3_s0")
    assert unscored.result is None and unscored.checks is None
    assert probe_runs.read_probe_run(tmp_path / "ppo_dtde_s0") is None


def test_the_overview_names_the_probe_runs(tmp_path):
    _probe_run(tmp_path / "probes_fast" / "ppo_ctde_p8a_s1")
    _probe_run(tmp_path / "probes_fast" / "ppo_ctde_p9_s0", scored=False)
    _probe_run(tmp_path / "market" / "ppo_ctde_s0", scored=False)
    service = ValidationService(ResultsService({"local": tmp_path}))
    table = service.rl_overview().set_index("run")
    assert table.loc["ppo_ctde_p8a_s1", ["probe", "result"]].tolist() == ["8a", "FAIL"]
    assert table.loc["ppo_ctde_p9_s0", "result"] == "not scored"
    assert table.loc["ppo_ctde_s0", ["probe", "result"]].tolist() == ["", ""]
    assert set(service.probe_runs(list(table.key))) == {
        "local/probes_fast/ppo_ctde_p8a_s1",
        "local/probes_fast/ppo_ctde_p9_s0",
    }
