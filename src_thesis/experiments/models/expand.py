"""From one experiment file to its runs.

Why: one file describes many runs (e.g. 3 paradigms × 3 algorithms × 3 seeds, possibly
times a sweep of six market mechanisms). This module turns that description into the
explicit list, so the count is visible before anything starts and every run can be
named.

An experiment expands to sweep points × paradigms × algorithms × seeds, plus
one run per sweep point, baseline and seed (02 §1, §3.10, §3.11).
"""

from __future__ import annotations

import copy
import itertools
import re
from dataclasses import dataclass, field
from typing import Any

from src_thesis.experiments.models.records import ExperimentFile, RunCell

DEFAULT_PARADIGMS = ["dtde"]
DEFAULT_ALGORITHMS = ["ppo"]
DEFAULT_SEEDS = [42]


@dataclass(frozen=True)
class SweepPoint:
    """One variant of a swept study.

    Attributes:
        label: Name of the variant, used in run IDs.
        overrides: Dotted path → value applied to the file for this variant.
    """

    label: str
    overrides: dict[str, Any] = field(default_factory=dict)  # dotted path -> value


def sweep_points(file: ExperimentFile) -> list[SweepPoint]:
    """The points of ``sweep`` (grid = Cartesian product, zip = paired lists)."""
    sweep = file.sweep or {}
    params: dict[str, list[Any]] = sweep.get("parameters") or {}
    if not params:
        return [SweepPoint("")]
    paths = list(params)
    if sweep.get("mode", "grid") == "zip":
        lengths = {len(v) for v in params.values()}
        if len(lengths) != 1:
            raise ValueError("sweep.mode 'zip' needs lists of equal length")
        combos = list(zip(*params.values()))
    else:
        combos = list(itertools.product(*params.values()))
    labels = sweep.get("labels") or [
        "_".join(_slug(v) for v in combo) for combo in combos
    ]
    if len(labels) != len(combos):
        raise ValueError(
            f"sweep.labels has {len(labels)} names for {len(combos)} points"
        )
    return [
        SweepPoint(label, dict(zip(paths, combo)))
        for label, combo in zip(labels, combos)
    ]


def apply_overrides(file: ExperimentFile, overrides: dict[str, Any]) -> ExperimentFile:
    """Return a copy with each dotted path (e.g. ``market.mechanism``) set."""
    data = copy.deepcopy(file.model_dump(mode="json"))
    for path, value in overrides.items():
        node = data
        *parents, leaf = path.split(".")
        for key in parents:
            node = node.setdefault(key, {})
        node[leaf] = value
    return ExperimentFile.model_validate(data)


def expand(file: ExperimentFile) -> list[RunCell]:
    """All runs a file asks for.

    Sweep points × paradigms × algorithms × seeds (kind ``train``), then sweep
    points × baselines × seeds (kind ``baseline``).

    Returns:
        One ``RunCell`` per run, in that order.
    """
    learning = file.learning or {}
    paradigms = learning.get("paradigms") or DEFAULT_PARADIGMS
    algorithms = learning.get("algorithms") or DEFAULT_ALGORITHMS
    seeds = learning.get("seeds") or DEFAULT_SEEDS
    cells = []
    for point in sweep_points(file):
        for paradigm, algorithm, seed in itertools.product(
            paradigms, algorithms, seeds
        ):
            cells.append(
                RunCell(
                    kind="train",
                    sweep_label=point.label,
                    sweep_point=point.overrides,
                    algorithm=algorithm,
                    paradigm=paradigm,
                    seed=seed,
                )
            )
        for baseline, seed in itertools.product(_baseline_names(file), seeds):
            cells.append(
                RunCell(
                    kind="baseline",
                    sweep_label=point.label,
                    sweep_point=point.overrides,
                    algorithm=baseline,
                    paradigm="-",
                    seed=seed,
                )
            )
    return cells


def run_id(experiment_id: str, cell: RunCell, file_hash: str) -> str:
    """``<meta.id>__<sweep-label>__<algo>-<paradigm>__s<seed>__<hash8>`` (03 §3)."""
    learner = (
        cell.algorithm if cell.kind != "train" else f"{cell.algorithm}-{cell.paradigm}"
    )
    parts = [
        experiment_id,
        cell.sweep_label or "base",
        learner,
        f"s{cell.seed}",
        file_hash[:8],
    ]
    return "__".join(_slug(p) for p in parts)


def _baseline_names(file: ExperimentFile) -> list[str]:
    names = []
    for entry in file.baselines or []:
        names.append(entry if isinstance(entry, str) else str(entry.get("name", "")))
    return [n for n in names if n]


def _slug(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9.-]+", "-", str(value)).strip("-") or "x"
