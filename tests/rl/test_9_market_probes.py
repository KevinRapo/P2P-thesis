"""Probes 7-10, the market's features one at a time: their exact answers hold.

Nothing is trained: each test plays the probe's best action and a few others and
checks the rewards and values the probe's ``checks`` promise.
"""

import numpy as np
import pytest

from core.rl.envs.probes import (
    ConditionalPartProbe,
    GatedActionProbe,
    LongEpisodeProbe,
    MutualChoiceProbe,
)
from core.rl.scripts.probe_check import PROBES

SCRAMBLED = {"n_agents": 3, "scramble_ids": True}


def _unit(value: float) -> np.ndarray:
    return np.array([value], dtype=np.float32)


def _best(env, check) -> dict:
    """The check's best action as the environment takes it."""
    actions = {}

    for agent, parts in check.action.items():
        actions[agent] = {
            name: (value if isinstance(value, int) else _unit(value))
            for name, value in parts.items()
        }

    return actions


def _rewards(env, actions) -> dict:
    env.reset(seed=0)
    _, rewards, *_ = env.step(actions)

    return rewards


def test_gated_best_answer_and_its_local_optimum():
    """Open at 0.5 with the agent's own category earns 1; a closed gate earns 0.2
    whatever the category; an open gate with another category earns 0."""
    env = GatedActionProbe(SCRAMBLED)
    check = env.checks(0.99)[0]
    best = _best(env, check)
    assert _rewards(env, best) == {a: pytest.approx(1.0) for a in env.agents_id}

    closed = {a: {"choice": 0, "gate": _unit(-0.5)} for a in env.agents_id}
    assert all(r == pytest.approx(0.2) for r in _rewards(env, closed).values())

    wrong = {
        a: {"choice": (env.choices[a] + 1) % 3, "gate": _unit(0.5)}
        for a in env.agents_id
    }
    assert all(r == 0.0 for r in _rewards(env, wrong).values())
    assert len(set(env.choices.values())) == 3


def test_mutual_choice_pays_only_together():
    """Mutual naming on the preferred sides earns 1.1 each; one side of a pair
    alone earns nothing; the DSO pays 0.5 (+0.1 on the own side) whatever the
    mate does."""
    env = MutualChoiceProbe({"n_agents": 4, "scramble_ids": True})
    check = env.checks(0.99)[0]
    best = _best(env, check)
    assert _rewards(env, best) == {a: pytest.approx(1.1) for a in env.agents_id}

    first, second = env.agents_id[:2]
    assert env.mate[first] == second and env.mate[second] == first

    alone = dict(best)
    alone[second] = {"side": env.preferred[second], "partner": env.NOBODY}
    rewards = _rewards(env, alone)
    assert rewards[first] == pytest.approx(0.1)  # its mate did not name it

    dso = {a: {"side": env.preferred[a], "partner": env.DSO} for a in env.agents_id}
    assert all(r == pytest.approx(0.6) for r in _rewards(env, dso).values())

    same_side = dict(best)
    same_side[second] = {"side": env.preferred[first], "partner": env.MATE}
    assert _rewards(env, same_side)[first] == pytest.approx(0.1)


def test_mutual_choice_needs_pairs():
    with pytest.raises(ValueError):
        MutualChoiceProbe({"n_agents": 3})


def test_conditional_part_level_follows_the_side():
    """The own side at its level earns 1.05; the other side at its own level 1.0;
    a level that ignores the side (0) earns less on either."""
    env = ConditionalPartProbe(SCRAMBLED)
    check = env.checks(0.99)[0]
    best = _best(env, check)
    assert _rewards(env, best) == {a: pytest.approx(1.05) for a in env.agents_id}

    other = {
        a: {"side": 1 - s, "level": _unit(env.level_for[1 - s])}
        for a, s in env.own_side.items()
    }
    assert all(r == pytest.approx(1.0) for r in _rewards(env, other).values())

    middle = {a: {"side": s, "level": _unit(0.0)} for a, s in env.own_side.items()}
    assert all(r == pytest.approx(0.8) for r in _rewards(env, middle).values())


def test_long_episode_values_are_the_discounted_end_reward():
    """24 steps, +1 at the last only, the hour in the observation: the discounted
    return from hour t is γ^(23 − t), as the checks state."""
    env = LongEpisodeProbe({"n_agents": 3})
    gamma = PROBES[10].gamma
    obs, _ = env.reset(seed=0)
    hours, rewards = [obs[env.agents_id[0]][0]], []

    for _ in range(env.length):
        obs, reward, terminated, truncated, _ = env.step(
            {a: _unit(0.0) for a in env.agents_id}
        )
        rewards.append(reward[env.agents_id[0]])
        hours.append(obs[env.agents_id[0]][0])

    assert terminated["__all__"] and not truncated["__all__"]
    assert rewards[-1] == 1.0 and sum(rewards) == 1.0
    assert hours[0] == 0.0 and hours[23] == pytest.approx(1.0)

    returns = {
        t: sum(gamma**k * r for k, r in enumerate(rewards[t:])) for t in range(24)
    }
    for check in env.checks(gamma):
        hour = round(check.obs[env.agents_id[0]][0] * 23)
        for value in check.value.values():
            assert value == pytest.approx(returns[hour])


def test_every_probe_has_a_budget_and_its_checks():
    """The check's table covers probes 1-10, each with checks it can score."""
    assert sorted(PROBES) == list(range(1, 11))

    for number, probe in PROBES.items():
        env = probe.env_class(dict(probe.env_config))
        assert env.checks(probe.gamma), f"probe {number} has no checks"
        assert probe.budget > 0
