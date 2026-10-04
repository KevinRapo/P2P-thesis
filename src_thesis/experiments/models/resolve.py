"""Filling defaults and fixing one run's world.

Why: users write short files and leave most values at their defaults. A run must not
depend on what the defaults happen to be later, so each run stores a fully filled-in
copy (``resolved.json``). If a default changes in the code, old runs still say exactly
what they used.

``resolve`` fills every unset field with its default from 02, so the manifest
records the values a run actually used. ``resolve_run`` additionally applies
one sweep point and fixes the learning plan to one cell. ``resolve_days``
turns the ``time.days`` section into explicit train and evaluation dates.
"""

from __future__ import annotations

import copy
import math
import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from src_thesis.experiments.models.expand import apply_overrides
from src_thesis.experiments.models.records import ExperimentFile, RunCell

# Defaults of 02-experiment-config.md §3 (only fields that have one).
DEFAULTS: dict[str, Any] = {
    "time": {
        "resolution": "hourly_aggregated",
        "horizon_steps": 24,
        "days": {"mode": "fixed", "filter": {}, "eval_holdout": 0.2, "seed": 42},
    },
    "grid": {
        "source": {"type": "simbench"},
        "background": {
            "mode": "mapped_replacement",
            "scale": 1.0,
            "profiles": "native",
        },
        "limits": {
            "v_min_pu": None,  # None = each bus's network limit (D-15)
            "v_max_pu": None,
            "line_max_percent": 100,
            "trafo_max_percent": 100,
        },
        "ratings": {"source": "network"},
        "power_flow": {"algorithm": "nr", "init": "results"},
        "reactive": {"load": "profile_ratio", "fallback_pf": 0.95},
        "assessment": {"mode": "feedback"},
    },
    "market": {
        "mechanism": "average",
        "price": {"min": 0, "max": 1000},
        "quantity": {"min": 0, "max": 1000},
        "partner_preference": False,
        "match_threshold": 1e-6,
        "ledger": {"enabled": True, "difficulty": 2},
        "async_orders": True,
    },
    "dso": {
        "tariffs": {
            "source": "synthetic",
            "mode": "normalized",
            "reset_per_episode": False,
        },
        "fees": {
            "charged": False,
            "congestion_factor": 0.5,
            "congestion_threshold": 0.8,
            "distance_factor": 0.35,
            "voltage_factor": 0.15,
            "voltage_threshold": 0.05,
            "instability_threshold": 0.2,
            "imbalance_factor": 0.15,
            "zone_factor": 0.15,
        },
    },
    "environment": {
        "observation": {
            "version": "v1",
            "forecast_error": 0.3,
            "forecast_anchors": 4,
            "own_bus_voltage": "private",
        },
        "reward": {
            "version": "corrected-v1",
            "log_scale": 20,
            # Eq. 4-6 and the penalty factors of the original reward.py.
            "base_weights": {
                "grid": 10.0,
                "resource": 1.5,
                "trading": 5.0,
                "stability": 2.0,
                "economic": 3.0,
            },
            "cooperation_weights": {
                "welfare": 7.0,
                "liquidity": 1.5,
                "spread": 1.5,
                "volatility": 3.0,
                "coordination": 5.0,
                "imbalance": 10.0,
                "congestion": 9.0,
                "convergence": 8.0,
                "self_consumption": 5.0,
                "flexibility": 6.0,
            },
            "penalties": {
                "dso": 15.0,
                "grid_imbalance": 10.0,
                "price_deviation": 2.0,
                "unutilized": 1.5,
                "volatility": 2.0,
                "no_trades": 5.0,
            },
            "contribution_weights": {"grid": 0.5, "price": 0.2, "local": 0.3},
        },
        "reputation": {
            "weights": {"reliability": 0.3, "fairness": 0.2, "grid": 0.5},  # eq. 12
            "decay": "time_of_day",
        },
    },
    "learning": {
        "paradigms": ["dtde"],
        "algorithms": ["ppo"],
        "seeds": [42],
        "budget": {"unit": "iterations", "value": 100},
        "model": {"embeddings_dim": 128, "activation": "relu"},
        "tuning": {"method": "pbt", "num_samples": 1},
        "checkpoint": {"every": 10, "keep": 3},
    },
    "evaluation": {
        "interval": 1,
        "episodes": "auto",
        "explore": False,
        "days": "holdout",
        "parallel_to_training": True,
    },
    "baselines": ["no_order", "random"],
    "resources": {"max_parallel_runs": 1},
    "outputs": {
        "record_steps": "evaluation",
        "grid_element_results": False,
        "figures": [],
    },
}

SEASONS = {
    "winter": {12, 1, 2},
    "spring": {3, 4, 5},
    "summer": {6, 7, 8},
    "autumn": {9, 10, 11},
}


@dataclass(frozen=True)
class DaySplit:
    """Training and evaluation dates (``YYYY-MM-DD``).

    Attributes:
        train: Dates the agents train on.
        eval: Held-out dates for evaluation, never trained on.
    """

    train: tuple[str, ...]
    eval: tuple[str, ...]


def resolve(file: ExperimentFile) -> ExperimentFile:
    """A copy with every unset field filled from ``DEFAULTS`` (set values win)."""
    data = file.model_dump(mode="json")
    for section, default in DEFAULTS.items():
        if isinstance(default, dict):
            data[section] = _merge(default, data.get(section) or {})
        elif not data.get(section):
            data[section] = copy.deepcopy(default)
    if any("placement_rule" in p for p in data.get("participants", [])):
        raise NotImplementedError(
            "participants.placement_rule needs the network (ProfileService, R3); "
            "list participants explicitly for now"
        )
    return ExperimentFile.model_validate(data)


def resolve_run(file: ExperimentFile, cell: RunCell) -> ExperimentFile:
    """One run's world: sweep point applied, learning fixed to the cell."""
    resolved = resolve(apply_overrides(file, cell.sweep_point))
    data = resolved.model_dump(mode="json")
    if cell.kind == "train":
        data["learning"].update(
            paradigms=[cell.paradigm], algorithms=[cell.algorithm], seeds=[cell.seed]
        )
    else:
        data["learning"].update(seeds=[cell.seed])
    return ExperimentFile.model_validate(data)


def resolve_days(time_section: dict[str, Any]) -> DaySplit:
    """Explicit train and evaluation dates from ``time.days`` (02 §3.2).

    ``fixed`` trains and evaluates on the same date, like the original. For
    ``range`` and ``sampler`` a seeded share (or list) of dates is held out for
    evaluation and never trained on.
    """
    days = time_section.get("days") or {}
    mode = days.get("mode", "fixed")
    if mode == "fixed":
        day = str(days["date"])
        return DaySplit((day,), (day,))
    start, end = date.fromisoformat(str(days["start"])), date.fromisoformat(
        str(days["end"])
    )
    if end < start:
        raise ValueError(f"time.days.end {end} is before start {start}")
    candidates = [start + timedelta(n) for n in range((end - start).days + 1)]
    if mode == "sampler":
        candidates = [d for d in candidates if _matches(d, days.get("filter") or {})]
    elif mode != "range":
        raise ValueError(f"unknown time.days.mode {mode!r}")
    if not candidates:
        raise ValueError("time.days selects no dates")
    all_days = [d.isoformat() for d in candidates]
    holdout = days.get("eval_holdout", 0.2)
    if isinstance(holdout, list):
        held = sorted(str(d) for d in holdout)
        missing = set(held) - set(all_days)
        if missing:
            raise ValueError(
                f"eval_holdout dates outside the window: {sorted(missing)}"
            )
    else:
        n_eval = min(len(all_days) - 1, math.ceil(float(holdout) * len(all_days)))
        shuffled = list(all_days)
        random.Random(days.get("seed", 42)).shuffle(shuffled)
        held = sorted(shuffled[: max(n_eval, 0)])
    train = tuple(d for d in all_days if d not in set(held))
    return DaySplit(train, tuple(held) or train)


def _matches(day: date, flt: dict[str, Any]) -> bool:
    if "season" in flt and day.month not in SEASONS[flt["season"]]:
        return False
    if "months" in flt and day.month not in set(flt["months"]):
        return False
    day_type = flt.get("day_type")
    if day_type == "workday" and day.weekday() >= 5:
        return False
    if day_type == "weekend" and day.weekday() < 5:
        return False
    return True


def _merge(default: dict[str, Any], given: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(default)
    for key, value in given.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out
