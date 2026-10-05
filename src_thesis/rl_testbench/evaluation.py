"""Held-out evaluation and random-policy baselines for benchmark cases.

Built with milestone 1 (rl-testbench.md §5). One rule across paradigms:
per-agent returns and one team score from the raw environment rewards, with
the aggregation (sum or mean) stated (I-60, I-73).
"""

from __future__ import annotations

from pathlib import Path

from src_thesis.rl_testbench.cases import BenchmarkCase


def evaluate(
    case: BenchmarkCase, checkpoint: Path, seeds: tuple[int, ...]
) -> dict[str, float]:
    """Per-agent and team scores of a restored checkpoint, exploration off."""
    raise NotImplementedError("Held-out evaluation is built with milestone 1")


def random_baseline(case: BenchmarkCase, seeds: tuple[int, ...]) -> dict[str, float]:
    """Scores of valid random actions on the same evaluation seeds."""
    raise NotImplementedError("Random baseline is built with milestone 1")
