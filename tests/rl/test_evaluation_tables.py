"""``core.rl.policy.evaluation``: every episode kept, per agent and per episode, and
the traced episodes step by step, from infos in the layout the module describes.
A small two-agent environment, no training."""

from __future__ import annotations

import math

import pytest

from core.rl.policy import evaluation


class Ledger:
    """Two agents, three steps per episode. Each step agent ``a`` earns its action,
    ``b`` twice it; the infos follow ``core/rl/policy.py``'s layout, and reset
    reports the day it was asked for."""

    def __init__(self, config=None) -> None:
        self.t = 0

    def reset(self, *, seed=None, options=None):
        self.t = 0
        self.day = (options or {}).get("day", "none")
        return {"a": 0.0, "b": 0.0}, {x: {"day": self.day} for x in "ab"}

    def step(self, actions):
        self.t += 1
        rewards = {"a": actions["a"], "b": 2 * actions["b"]}
        shared = {"volume_kwh": 10.0}
        infos = {
            x: {
                "bought_kwh": 1.0,
                "state": {"soc": 0.1 * self.t},
                "shared": shared,
                "shared_state": {"price": float(self.t)},
            }
            for x in "ab"
        }
        done = self.t >= 3
        terminated = {"a": done, "b": done, "__all__": done}

        return {"a": 0.0, "b": 0.0}, rewards, terminated, {"__all__": False}, infos


def one(obs):
    return {"a": 1.0, "b": 1.0}


def nothing(obs):
    return {"a": 0.0, "b": 0.0}


@pytest.fixture()
def found():
    return evaluation(
        Ledger,
        {},
        {"one": one, "nothing": nothing},
        [7, 8],
        options=[{"day": "d1"}, {"day": "d2"}],
        trace=[1],
    )


def test_the_summary_is_as_before(found):
    one_row = found.summary.set_index("policy").loc["one"]
    assert one_row["team_return_mean"] == 9.0  # 3 steps of 1 + 2
    assert one_row["return/b"] == 6.0 and one_row["episodes"] == 2


def test_one_row_per_policy_episode_and_agent(found):
    agents = found.agents
    assert len(agents) == 2 * 2 * 2
    row = agents[
        (agents.policy == "one") & (agents.episode == 1) & (agents.agent == "b")
    ]
    assert row.iloc[0].to_dict() == {
        "policy": "one",
        "episode": 1,
        "seed": 8,
        "day": "d2",  # from reset
        "agent": "b",
        "return": 6.0,
        "bought_kwh": 3.0,  # summed over the steps
    }
    assert "soc" not in agents and "volume_kwh" not in agents  # states, shared


def test_one_row_per_policy_and_episode(found):
    episodes = found.episodes
    assert episodes[["policy", "episode", "day"]].values.tolist() == [
        ["one", 0, "d1"],
        ["one", 1, "d2"],
        ["nothing", 0, "d1"],
        ["nothing", 1, "d2"],
    ]
    assert episodes.team_return.tolist() == [9.0, 9.0, 0.0, 0.0]
    assert episodes.volume_kwh.tolist() == [30.0] * 4  # shared, counted once
    assert "price" not in episodes  # a state


def test_only_the_traced_episodes_step_by_step(found):
    steps, agents = found.trace_steps, found.trace_agents
    assert set(steps.episode) == {1} and len(steps) == 2 * 3
    assert steps[steps.policy == "one"].team_reward.tolist() == [3.0] * 3
    assert steps.price.tolist() == [1.0, 2.0, 3.0] * 2
    assert len(agents) == 2 * 3 * 2
    soc = agents[(agents.policy == "one") & (agents.agent == "a")].soc.tolist()
    assert soc == pytest.approx([0.1, 0.2, 0.3])
    assert math.isclose(agents.reward.sum(), 9.0)


def test_nothing_traced_means_no_trace_tables():
    plain = evaluation(Ledger, {}, {"one": one}, [1])
    assert plain.trace_steps is None and plain.trace_agents is None
    assert plain.agents.day.tolist() == ["none", "none"]  # no options
