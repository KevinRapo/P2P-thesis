"""Focused inference-path tests (P2-02)."""

import numpy as np
import torch
from ray.rllib.core import Columns

from src.environment.inference import RLInference


class _Distribution:
    def sample(self):
        return torch.tensor([[0.25, -0.5]])

    def to_deterministic(self):
        return self


class _DistributionClass:
    @staticmethod
    def from_logits(_logits):
        return _Distribution()


class _Module:
    def __init__(self) -> None:
        self.calls = []

    def forward_inference(self, batch):
        self.calls.append(batch)
        return {Columns.ACTION_DIST_INPUTS: torch.zeros((1, 4))}

    def get_inference_action_dist_cls(self):
        return _DistributionClass


class _Algorithm:
    def __init__(self) -> None:
        self.modules = {"a": _Module(), "b": _Module()}

    def get_module(self, module_id=None):
        return self.modules[module_id]


def test_inference_uses_restored_registered_modules_with_agent_policy_ids() -> None:
    inference = object.__new__(RLInference)
    inference._grouped = False
    inference.exploration = False
    inference.algorithm = _Algorithm()

    actions = inference._compute_actions({"a": np.array([1.0]), "b": np.array([2.0])})

    assert set(actions) == {"a", "b"}
    assert np.allclose(actions["a"], [0.25, -0.5])
    assert np.allclose(actions["b"], [0.25, -0.5])
    assert all(module.calls for module in inference.algorithm.modules.values())


def test_inference_reads_shared_environment_info_from_agent_envelope() -> None:
    info = {"a": {"market_price": 3.0, "market_volume": 2.0},
            "b": {"market_price": 3.0, "market_volume": 2.0}}

    assert RLInference._episode_info(info) == info["a"]


def test_inference_close_stops_algorithm_without_shutting_a_caller_owned_ray_session(monkeypatch) -> None:
    inference = object.__new__(RLInference)

    class _ClosableAlgorithm:
        stopped = False

        def stop(self):
            self.stopped = True

    inference.algorithm = _ClosableAlgorithm()
    inference._owns_ray = False
    monkeypatch.setattr("src.environment.inference.ray.is_initialized", lambda: True)
    shutdown_called = []
    monkeypatch.setattr("src.environment.inference.ray.shutdown", lambda: shutdown_called.append(True))

    inference.close()

    assert inference.algorithm.stopped
    assert not shutdown_called
