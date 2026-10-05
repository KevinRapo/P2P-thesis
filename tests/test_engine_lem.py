"""The original market behind the MarketEngine seam, built from a preset."""

import json
from pathlib import Path

import pytest

from src_thesis.marlem.core.engine import (
    AgentSpec,
    BatterySpec,
    EngineSpec,
    MarketSpec,
    TariffSpec,
)
from src_thesis.marlem.environment.build import build_engine
from src_thesis.marlem.policies.registry import get_policy

PRESETS = (
    Path(__file__).resolve().parents[1] / "src_thesis/platform/experiments/presets"
)


def spec(steps: int = 24, battery: bool = True) -> EngineSpec:
    """Two agents on a made-up day: a producer with a battery and a consumer."""
    gen = tuple(max(0.0, 8.0 - abs(h - 12)) for h in range(steps))
    dem = tuple(2.0 for _ in range(steps))
    return EngineSpec(
        agents=(
            AgentSpec(
                "prod",
                "b1",
                10.0,
                gen,
                (0.5,) * steps,
                BatterySpec(20.0, 0.1, 0.9, initial_soc=0.5) if battery else None,
            ),
            AgentSpec("cons", "b2", 10.0, (0.0,) * steps, dem),
        ),
        market=MarketSpec(
            0.05, 0.5, 0.0, 50.0, ledger_difficulty=1, async_orders=False
        ),
        tariffs=TariffSpec(),
        steps=steps,
        seed=3,
        day="2016-06-01",
    )


def run(engine, policy_name: str, seed: int = 3):
    policy = get_policy(policy_name)
    policy.reset(seed)
    engine.reset(seed)
    outcomes = []
    for _ in range(engine.n_steps):
        outcomes.append(engine.step(policy.act(engine.views())))
    return outcomes


@pytest.mark.parametrize("name", ["no_order", "random", "net_position"])
def test_all_steps_of_the_day_are_played(name: str) -> None:
    outcomes = run(build_engine(spec()), name)
    assert [o.step for o in outcomes] == list(range(24))  # I-01: 24, not 23


def test_profiles_are_the_ones_given() -> None:
    outcomes = run(build_engine(spec()), "no_order")
    assert outcomes[12].generation_kwh["prod"] == pytest.approx(8.0)
    assert outcomes[0].demand_kwh["cons"] == pytest.approx(2.0)


def test_the_battery_starts_where_the_spec_says() -> None:
    engine = build_engine(spec())
    engine.reset(3)
    assert engine.views()["prod"].soc_kwh == pytest.approx(10.0)
    assert engine.views()["cons"].soc_kwh is None


def test_net_position_trades_and_orders_are_recorded() -> None:
    outcomes = run(build_engine(spec()), "net_position")
    noon = outcomes[12]
    sides = {o["agent_id"]: o["is_buy"] for o in noon.orders}
    assert sides == {"prod": False, "cons": True}
    assert all(o["quantity_kwh"] > 0 for o in noon.orders)  # not the residual (I-12)
    assert sum(t["quantity_kwh"] for t in noon.trades) > 0


def test_same_seed_same_day() -> None:
    first = run(build_engine(spec()), "random", seed=5)
    second = run(build_engine(spec()), "random", seed=5)
    assert first == second


def test_a_second_reset_replays_the_day() -> None:
    engine = build_engine(spec())
    assert run(engine, "net_position") == run(engine, "net_position")


def test_the_factory_builds_a_preset_day() -> None:
    from src_thesis.platform.experiments.factory.environment import build_engine_spec
    from src_thesis.platform.experiments.models.records import ExperimentFile
    from src_thesis.platform.experiments.models.resolve import resolve

    data = json.loads((PRESETS / "case6-3x3.marlem.json").read_text("utf-8"))
    built = build_engine_spec(resolve(ExperimentFile.model_validate(data)))
    assert len(built.agents) == len(data["participants"]) and built.steps == 24
    assert all(len(a.generation_kwh) == 24 for a in built.agents)
    outcomes = run(build_engine(built), "net_position", seed=1)
    assert len(outcomes) == 24
