"""``results.validation_scores``: the VTI on the validation days (RP-7c, MP-1c)."""

import json

import pandas as pd
import pytest

from core.runner.results import validation_scores


def test_the_validation_vti_divides_sums_over_days_against_each_days_references(
    tmp_path,
):
    # P1 has PV on d1 and demand on d2; P2 a 10 kWh battery at 5 kWh each morning.
    # Each day on its own, the battery may end empty (MP-1c):
    #   ceiling d1: 2 + 5 kWh exported at 0.1 = 0.7; d2: 2 kWh to P1, 3 exported = 0.3
    #   alone   d1: P1 0.2, P2 0.5 = 0.7;            d2: P1 -1.0, P2 0.5 = -0.5
    # reach (0.7 + 0.3) - (0.7 - 0.5) = 0.8
    battery = dict(capacity_kwh=10.0, min_soc=0.0, max_soc=1.0, charge_efficiency=1.0,
                   discharge_efficiency=1.0, initial_soc=0.5, max_power_kw=100.0)
    scenario = {"grid": {"step_hours": 1.0},
                "participants": [{"id": "P1", "battery": None},
                                 {"id": "P2", "battery": battery}]}
    (tmp_path / "scenario.json").write_text(json.dumps(scenario), encoding="utf-8")
    profiles = {"d1": {"P1": (2.0, 0.0)}, "d2": {"P1": (0.0, 2.0)}}
    agent_steps = pd.DataFrame(
        [
            {"env_steps": 0, "policy": "net_position", "period": "w", "day": day,
             "step": 0, "agent": agent, "generation_kwh": gen, "demand_kwh": demand}
            for day in ("d1", "d2")
            for agent, (gen, demand) in (
                ("P1", profiles[day]["P1"]), ("P2", (0.0, 0.0))
            )
        ]
    )
    steps = pd.DataFrame(
        [{"env_steps": 0, "policy": "net_position", "period": "w", "day": day,
          "step": 0, "feed_in_tariff": 0.1, "utility_price": 0.5}
         for day in ("d1", "d2")]
    )
    # The trained team: energy money 0.65 and -0.2 (bills 0.6 and -0.3 after fees).
    agents = pd.DataFrame(
        [
            {"env_steps": 0, "policy": "trained", "period": "w", "day": "d1",
             "agent": "P1", "bill": 0.6, "fees": 0.05},
            {"env_steps": 0, "policy": "trained", "period": "w", "day": "d2",
             "agent": "P1", "bill": -0.3, "fees": 0.1},
        ]
    )
    agent_steps.to_csv(tmp_path / "validation_agent_steps.csv", index=False)
    steps.to_csv(tmp_path / "validation_steps.csv", index=False)
    agents.to_csv(tmp_path / "validation_agents.csv", index=False)
    scores = validation_scores(tmp_path).set_index("period")
    assert scores.loc["all", "vti"] == pytest.approx((0.45 - 0.2) / 0.8)
    assert scores.loc["all", "vti_after_fees"] == pytest.approx((0.3 - 0.2) / 0.8)
    assert scores.loc["all", "days"] == 2
    assert scores.loc["w", "vti"] == pytest.approx(scores.loc["all", "vti"])


def test_no_validation_tables_no_scores(tmp_path):
    assert validation_scores(tmp_path) is None
