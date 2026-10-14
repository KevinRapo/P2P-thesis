"""The grid fees of a step price the step's own power flow.

The DSO charges the fees (eq. 8) after the step's power flow, so the congestion
and thermal parts of every trade use the line loading that the step's trades
caused, also in the first step of the day.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import store
from core.market.dso.dso import DSO_ID
from core.market.lem import LocalEnergyMarket

SCENARIO = Path(__file__).resolve().parents[2] / "scenarios/validate_market.json"


@pytest.fixture(scope="module")
def played():
    scenario = store.load(SCENARIO)
    # The scenario's lines stay below 20 % loading; a low thermal threshold makes
    # the thermal fee depend on the loading in every step.
    scenario.dso.thermal_threshold = 0.02
    market = LocalEnergyMarket(scenario)
    market.reset()
    return market, market.run_to_end()


def test_fees_see_the_same_steps_power_flow(played):
    market, records = played
    dso = market.dso
    assert any(t.fee_parts.thermal > 0 for r in records for t in r.trades)
    for record in records:
        loading = record.grid.line_loading_percent
        for t in record.trades:
            if DSO_ID in (t.buyer_id, t.seller_id):
                other = t.seller_id if t.buyer_id == DSO_ID else t.buyer_id
                path = market._upstream(other)
            else:
                path = market._path(t.buyer_id, t.seller_id)
            highest = max((loading.get(x, 0.0) for x in path.lines), default=0.0)
            c = min(1.0, highest / 100)
            expected = 0.0
            if c > dso.thermal_threshold:
                f = (c - dso.thermal_threshold) / (1 - dso.thermal_threshold)
                expected = min(f, dso.thermal_cap) * t.quantity * t.price
            assert t.fee_parts.thermal == pytest.approx(expected, abs=1e-12)


def test_first_step_is_charged_like_any_other(played):
    _, records = played
    first = records[0]
    assert first.grid.line_loading_percent, "the first step has a power flow"
    assert all(t.fees == pytest.approx(t.fee_parts.total) for t in first.trades)
    paid = sum(o.fees for o in first.participants.values())
    assert paid == pytest.approx(sum(t.buyer_fee + t.seller_fee for t in first.trades))
