"""Restructuring must not change behaviour: fixed-seed episodes replay exactly.

The reference (``golden/episodes.json``) was recorded before the code was split
into modules; ``golden/episode_trace.py`` replays the same scenarios.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "golden"))
from episode_trace import FILE, scenarios, trace  # noqa: E402

pytest.importorskip("ray")


@pytest.fixture(scope="module")
def replay() -> dict:
    return json.loads(json.dumps(trace(), sort_keys=True))


@pytest.mark.parametrize("name", list(scenarios()))
def test_episode_replays_exactly(replay, name) -> None:
    golden = json.loads(FILE.read_text(encoding="utf-8"))[name]
    assert len(replay[name]) == len(golden)
    for step, (now, then) in enumerate(zip(replay[name], golden)):
        assert now == then, f"{name}: first difference at step {step}"
