"""The RL testbench: its cases drive MARLEM's own RLTrainer, and runs record the
same provenance as market runs (validation/rl-testbench.md).
"""

import json

import pytest

pytest.importorskip("ray")

from src_thesis.marlem.marl.train import GroupedLEM, RLTrainer, agent_ids  # noqa: E402
from src_thesis.platform.testbench.cases import CASES, trainer  # noqa: E402
from src_thesis.platform.testbench.reporting import write_manifest  # noqa: E402


def test_cases_declare_known_paradigms() -> None:
    for case in CASES.values():
        assert case.paradigms and set(case.paradigms) <= {"dtde", "ctce", "ctde"}


@pytest.mark.parametrize("paradigm", ["dtde", "ctce", "ctde"])
def test_marlem_trainer_builds_every_paradigm_on_an_external_env(paradigm) -> None:
    case = CASES["multiagent_cartpole"]
    rl = trainer(case, "ppo", paradigm, cpus=1, gpus=0)
    assert isinstance(rl, RLTrainer) and not rl.is_market
    config = rl._setup_training_config(
        rl._setup_extra_config(rl._setup_algorithm_config())
    )
    assert config.env is not None
    if paradigm == "dtde":
        assert agent_ids(rl.env) == [0, 1]
        assert set(config.policies) == {"0", "1"}  # RLlib needs string IDs
    else:
        assert isinstance(rl.env, GroupedLEM)
        assert rl.env.original_agents_id == [0, 1]


def test_trainer_rejects_a_paradigm_the_case_does_not_test() -> None:
    with pytest.raises(ValueError, match="tests"):
        trainer(CASES["cartpole"], "ppo", "ctde")


def test_simple_spread_explains_its_missing_dependencies() -> None:
    try:
        import mpe2  # noqa: F401
    except ImportError:
        with pytest.raises(ImportError, match="mpe2"):
            CASES["simple_spread"].env_cls()
    else:
        pytest.skip("mpe2 is installed")


def test_manifest_records_run_code_and_versions(tmp_path) -> None:
    run = {"algorithm": "ppo", "paradigm": "dtde", "seed": 7, "env": {"num_agents": 1}}
    path = write_manifest("cartpole", run, tmp_path, {"return_mean": 1.0})
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["kind"] == "rl-benchmark" and data["case"] == "cartpole"
    assert data["run"]["seed"] == 7
    assert set(data["code"]) == {"commit", "dirty", "diff_sha256"}
    assert {"ray", "torch", "mpe2"} <= set(data["environment"]["packages"])
