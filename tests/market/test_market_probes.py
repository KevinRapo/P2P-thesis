"""The market probes (``core/market/probes.py``): every check of every probe passes
on the power flow."""

from __future__ import annotations

import pytest

from core.market import probes


@pytest.fixture(scope="module")
def runs() -> dict:
    return {r.probe.key: r for r in probes.play_all()}


@pytest.mark.parametrize("probe", [p.key for p in probes.PROBES])
def test_probe_passes(runs, probe):
    run = runs[probe]
    failed = [c for c in run.checks if not c.ok]
    assert run.records and run.checks
    assert not failed, "\n".join(
        f"step {c.step}: {c.name}: expected {c.expected}, got {c.got}" for c in failed
    )


def test_the_window_plays_the_probes_orders(runs):
    run = runs["M3"]
    assert [r.step for r in run.records] == list(probes.WINDOW)
    assert all(
        {o.agent_id for o in r.orders} == {"PV1", "PV2", "C1", "C2"}
        for r in run.records
    )
