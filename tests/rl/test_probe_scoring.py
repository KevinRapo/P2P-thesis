"""How the probe check judges a trained policy's outputs (``probe_check.compare``
and ``verdict``), without training: the outputs are given by hand."""

import numpy as np
import pandas as pd
import pytest

from core.rl.ctce import GROUP
from core.rl.envs.probes import Check, Follows
from core.rl.scripts.probe_check import TOLERANCE, compare, verdict


def _frame(rows) -> pd.DataFrame:
    frame = pd.DataFrame(
        rows, columns=["state", "output", "expected", "got", "tolerance"]
    )
    frame["error"] = (frame.got - frame.expected).abs()
    frame["ok"] = frame.error <= frame.tolerance + 1e-9

    return frame


def _unit(value: float) -> np.ndarray:
    return np.array([value], dtype=np.float32)


OBS = {"a": _unit(0.0), "b": _unit(0.0)}


def test_follows_judges_the_level_against_the_chosen_side():
    """Either side passes when the level matches it; the side itself (None) is not
    judged; a level matching the other side fails."""
    level = Follows("side", {0: -0.5, 1: 0.5})
    check = Check("obs 0", OBS, action={a: {"side": None, "level": level} for a in OBS})
    actions = {
        "a": {"side": 0, "level": _unit(-0.45)},  # sell, at sell's target
        "b": {"side": 1, "level": _unit(0.55)},  # buy, at buy's target
    }
    rows = compare(check, None, actions, "dtde")
    assert [r[1] for r in rows] == ["action a level", "action b level"]
    assert [r[2] for r in rows] == [-0.5, 0.5]
    assert verdict(_frame(rows))[0] == "PASS"

    actions["b"] = {"side": 1, "level": _unit(-0.5)}  # buy, at sell's target
    assert verdict(_frame(compare(check, None, actions, "dtde")))[0] == "FAIL"


def test_relative_tolerance_scales_with_the_value():
    """V = 0.31 with ``relative``: 0.15 · 0.31 = 0.047, so 0.20 fails, where the
    absolute tolerance (0.15) would have passed it."""
    value = {"a": 0.31, "b": 0.31}
    got = {"a": 0.20, "b": 0.31}
    relative = Check("hour 0", OBS, value=value, relative=True)
    absolute = Check("hour 0", OBS, value=value)

    rows = compare(relative, got, None, "dtde")
    assert rows[0][4] == pytest.approx(TOLERANCE * 0.31)
    assert verdict(_frame(rows))[0] == "FAIL"
    assert verdict(_frame(compare(absolute, got, None, "dtde")))[0] == "PASS"


def test_ctce_value_is_the_sum_and_a_missed_category_is_infinitely_far():
    """CTCE's one value is compared with the agents' sum (2 × 1.1); a wrong partner
    category is a miss, infinitely far, whatever its index."""
    check = Check(
        "obs 0",
        OBS,
        value={"a": 1.1, "b": 1.1},
        action={"a": {"side": 0, "partner": 0}, "b": {"side": 1, "partner": 0}},
    )
    actions = {"a": {"side": 0, "partner": 1}, "b": {"side": 1, "partner": 0}}
    rows = compare(check, {GROUP: 2.2}, actions, "ctce")
    assert rows[0][1:3] == (f"value {GROUP}", pytest.approx(2.2))
    result, worst = verdict(_frame(rows))
    assert result == "FAIL" and np.isinf(worst)
