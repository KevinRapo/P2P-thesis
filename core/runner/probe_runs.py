"""The RL probe runs: what each probe is, and what a probe run scored.

Plain data and file reading, next to the runner's other readers, so the Studio (the
Validate → RL probes page) reads it without loading Ray: everything under
``core/rl/`` imports Ray and torch. The probes themselves are in
``core/rl/envs/probes.py``, their procedure in ``core/rl/scripts/probe_check.py``,
the prose in ``docs/rl/probes.md``.

A probe run is a folder ``ppo_<paradigm>_p<probe>_s<seed>[_x<scale>]`` under
``runs/probes_<preset>/``; ``probe_check.score_to_file`` writes its ``score.csv``
(one row: result PASS, FAIL or MEASURED and ``worst``) and ``checks.csv`` (one row
per checked output: state, output, expected, got, tolerance, error, ok).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

RUN_NAME = re.compile(
    r"^ppo_(?P<paradigm>[a-z]+)_p(?P<probe>\d+[ab]?)_s(?P<seed>\d+)"
    r"(?:_x(?P<scale>[\d.]+))?$"
)


# --------------------------------------------------------------------------------------
# What each probe is
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class About:
    """One probe in words.

    Attributes:
        name: Short name (as ``probe_check.PROBES``).
        tests: The piece of learning it isolates.
        setup: Observation, action and reward.
        answer: The exact answer the trained networks must give.
        expect: What a correct learner shows, with its known limits.
        market: The market feature it stands for.
    """

    name: str
    tests: str
    setup: str
    answer: str
    expect: str
    market: str


ABOUT: dict[str, About] = {
    "1": About(
        "Constant",
        "Value learning: the reward reaches the learner, the episode's end is final, "
        "the value loss fits a constant.",
        "Observation 0, one step, reward +1 whatever the action; three agents.",
        "V = 1 per agent (3 for CTCE's group).",
        "Reached almost exactly by any working learner.",
        "The base of every value the market's critics learn.",
    ),
    "2": About(
        "Observation",
        "The observation reaches the critic, and the right agent's critic.",
        "Each agent observes +1 or −1 at random; reward = its own observation; one "
        "step. Checked all +1, all −1 and mixed.",
        "V(o) = o per agent (the sum for CTCE's group).",
        "The mixed state fails for a critic that ignores its input or reads another "
        "agent's observation.",
        "Each participant's critic reads its own 42 signals.",
    ),
    "3": About(
        "Discount",
        "Bootstrapping from the next state, the discount, where the episode ends.",
        "Two steps: observation 0 then 1; reward 0 then +1; γ = 0.5.",
        "V(1) = 1, V(0) = γ = 0.5 per agent.",
        "Exact for any working learner.",
        "Steps that pay later in the day.",
    ),
    "4": About(
        "Action",
        "The policy gradient, and each agent's action reaching its own reward.",
        "Observation 0, one step, continuous action; reward 1 − (a − t_i)² with "
        "targets −0.6, 0, 0.6; agents named out of sorted order.",
        "Action mean = t_i.",
        "A small overshoot towards the bounds is expected: samples beyond ±1 are "
        "clipped and earn the bound's reward.",
        "The continuous price and quantity.",
    ),
    "5": About(
        "Obs -> action",
        "Each policy uses its own observation; observation, action and reward stay "
        "aligned through batching.",
        "Each agent observes ±1; reward 1 − (a − o/2)²; one step.",
        "Action mean = o/2 (±0.5).",
        "CTCE is the slowest: one network must learn which observation matters for "
        "which agent from the summed reward (L-02).",
        "Prices and quantities that depend on the state of the market.",
    ),
    "6": About(
        "Mixed action",
        "A categorical and a continuous part learned at once.",
        "Observation 0, one step; action {choice: 3 categories, level}; reward "
        "[choice = c_i] + 1 − (level − t_i)².",
        "Most likely choice c_i (exactly), level mean t_i, V = 2.",
        "May need twice the budget in CTDE and DTDE.",
        "The market's action: side and partner categorical, quantity and price "
        "continuous ([P1] eq. 2).",
    ),
    "7": About(
        "Gated action",
        "A part that counts only when another part allows it, and a local optimum.",
        "Action {choice, gate}: a closed gate (g < 0) pays 0.2; an open gate pays "
        "[choice = c_i] · (1 − (g − 0.5)²).",
        "Choice c_i, gate mean 0.5, V = 1.",
        "A gate below 0 is the 'never order' optimum; CTCE is slow here.",
        "The no-order threshold: below it side, price and partner have no effect.",
    ),
    "8a": About(
        "Mutual choice, coordination",
        "Coordinating with a partner when coordinating is the better bet.",
        "Four agents in two pairs, action {side, partner: mate / DSO / nobody}; 1 "
        "when both name each other on opposite sides, 0.1 for the DSO, +0.1 for "
        "the own side.",
        "Own side, the mate, V = 1.1.",
        "Every working learner coordinates (the DSO pays less than mutual naming at "
        "random, 1/6); a failure points at the partner plumbing.",
        "Stage 1: a buyer and a seller trade there only if they name each other.",
    ),
    "8b": About(
        "Mutual choice, stag hunt",
        "The market's coordination problem: a safe option against a better one "
        "that needs the partner too.",
        "As 8a, but the DSO pays 0.5.",
        "None judged: the share of pairs that coordinate is measured.",
        "Independent learners are expected to choose the DSO (risk-dominant); CTCE "
        "may coordinate a pair.",
        "Naming a partner against leaving the order to the DSO.",
    ),
    "9": About(
        "Conditional part",
        "A continuous part whose best value depends on a categorical part.",
        "Action {side, level}; reward 1 − (level − t_side)², t_sell = −0.5, "
        "t_buy = +0.5, +0.05 for the own side.",
        "Either side, with its own level (judged against the chosen side's target); "
        "V = 1.05.",
        "A level near 0 is the compromise of an undecided side; RLlib's default head "
        "fails here, a state-independent log σ (variant SM) passes.",
        "An ask is not a bid: price and quantity depend on the side.",
    ),
    "10": About(
        "Long episode",
        "Discounting and bootstrapping over a whole day.",
        "24 steps, observation t/23, +1 at the last step; γ = 0.95.",
        "V(t) = 0.95^(23 − t): 0.31, 0.57 and 1 at hours 0, 12, 23 (within 15 %).",
        "Passes in every paradigm.",
        "The market's episode: one day of 24 hourly steps.",
    ),
}


# --------------------------------------------------------------------------------------
# What a probe run scored
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ProbeRunInfo:
    """A probe run's probe and its score, from its folder.

    Attributes:
        probe: The probe (``"1"`` ... ``"10"``, ``"8a"``, ``"8b"``).
        paradigm: CTCE, CTDE or DTDE.
        seed: The training seed.
        scale: Times the preset's budget (1 unless escalated).
        score: ``score.csv`` (one row), None before the run is scored.
        checks: ``checks.csv``, None before the run is scored.
    """

    probe: str
    paradigm: str
    seed: int
    scale: float
    score: Optional[pd.DataFrame]
    checks: Optional[pd.DataFrame]

    @property
    def about(self) -> Optional[About]:
        return ABOUT.get(self.probe)

    @property
    def result(self) -> Optional[str]:
        """PASS, FAIL or MEASURED; None before the run is scored."""
        return None if self.score is None else str(self.score.result.iloc[0])

    @property
    def worst(self) -> Optional[float]:
        """The worst error over its tolerance (above 1 fails), or a measured probe's
        share of coordinating pairs."""
        return None if self.score is None else float(self.score.worst.iloc[0])


def _csv(path: Path) -> Optional[pd.DataFrame]:
    try:
        return pd.read_csv(path) if path.is_file() else None
    except (OSError, ValueError, pd.errors.EmptyDataError):
        return None


def read_probe_run(folder: Path) -> Optional[ProbeRunInfo]:
    """The probe run in ``folder``, None when the folder is not one (by its name)."""
    folder = Path(folder)
    name = RUN_NAME.match(folder.name)

    if name is None:
        return None

    return ProbeRunInfo(
        probe=name["probe"],
        paradigm=name["paradigm"],
        seed=int(name["seed"]),
        scale=float(name["scale"] or 1.0),
        score=_csv(folder / "score.csv"),
        checks=_csv(folder / "checks.csv"),
    )
