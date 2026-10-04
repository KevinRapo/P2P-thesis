"""ResultService: reading finished runs (04 §5).

Final implementation: ``StoreResultService``, not built yet (R7). Demo:
``DemoResultService`` (generated sample results).
"""

from __future__ import annotations

import math
import random
from typing import Protocol
from src_thesis.application.config_service import ALGORITHMS, PARADIGMS
from src_thesis.application.profile_service import HOURS
from src_thesis.application.models import (
    MatrixTable,
    RunResult,
    Series,
)


# ---------------------------------------------------------------------- protocol
class ResultService(Protocol):
    """Reading finished runs: outcomes, learning curves, replays, comparisons."""

    def summary(self, run_id: str) -> RunResult:
        """Research outcomes, RL return and manifest of one run."""
        ...

    def training_curve(self, run_id: str) -> Series:
        """Training and evaluation return per iteration."""
        ...

    def step_records(self, run_id: str, episode: int = 0) -> list[dict]:
        """Orders, trades, settlement and grid assessment per step of one episode."""
        ...

    def grid_series(self, run_id: str, episode: int = 0) -> Series:
        """Voltages, loadings, losses and violations over one episode."""
        ...

    def agent_series(self, run_id: str, episode: int = 0) -> Series:
        """Per-agent state of charge, net injection and profit over one episode."""
        ...

    def matrix(self, experiment_id: str, metric: str) -> MatrixTable:
        """Paradigm × algorithm table of ``metric`` (mean ± std over seeds)."""
        ...

    def compare(self, run_ids: list[str], metric: str) -> Series:
        """One metric of several runs, for overlaying."""
        ...

    def export(self, run_ids: list[str], fmt: str = "csv") -> str:
        """Write the runs' raw series to a file.

        Args:
            run_ids: Runs to export.
            fmt: ``"csv"`` or ``"json"``.

        Returns:
            The path written.
        """
        ...


# ---------------------------------------------------------------------- final implementation (skeleton)
_NOT_BUILT = (
    "Not built yet: the final implementation of this service waits for its "
    "roadmap phase; the Studio uses the demo implementation until then."
)


class StoreResultService:
    """The final ``ResultService``: reads run folders from the experiment store (R7).

    Not implemented yet; every method raises.
    """

    def summary(self, run_id: str) -> RunResult:
        """Will read ``manifest.json`` and ``metrics/evaluation.jsonl``."""
        raise NotImplementedError(_NOT_BUILT)

    def training_curve(self, run_id: str) -> Series:
        """Will read ``metrics/training.csv``."""
        raise NotImplementedError(_NOT_BUILT)

    def step_records(self, run_id: str, episode: int = 0) -> list[dict]:
        """Will read ``raw/steps.jsonl`` with ``ExperimentStore.read_jsonl``."""
        raise NotImplementedError(_NOT_BUILT)

    def grid_series(self, run_id: str, episode: int = 0) -> Series:
        """Will build voltage, loading and violation series from the step records."""
        raise NotImplementedError(_NOT_BUILT)

    def agent_series(self, run_id: str, episode: int = 0) -> Series:
        """Will build per-agent series from the step records."""
        raise NotImplementedError(_NOT_BUILT)

    def matrix(self, experiment_id: str, metric: str) -> MatrixTable:
        """Will aggregate ``metric`` over seeds per paradigm × algorithm."""
        raise NotImplementedError(_NOT_BUILT)

    def compare(self, run_ids: list[str], metric: str) -> Series:
        """Will overlay ``metric`` of several runs; flags different reward versions."""
        raise NotImplementedError(_NOT_BUILT)

    def export(self, run_ids: list[str], fmt: str = "csv") -> str:
        """Will write the runs' raw series to ``<workspace>/exports``."""
        raise NotImplementedError(_NOT_BUILT)


# ---------------------------------------------------------------------- demo implementation
class DemoResultService:
    """Demo ``ResultService``: generated sample results. Shown as DEMO DATA in the
    Studio.
    """

    def summary(self, run_id: str) -> RunResult:
        """Sample-data version of ``ResultService.summary``."""
        rng = random.Random(run_id)
        return RunResult(
            run_id=run_id,
            rl_return=round(rng.uniform(5, 25), 2),
            outcomes={
                "served_demand_share": round(rng.uniform(0.9, 1.0), 3),
                "unmet_demand_kwh": round(rng.uniform(0, 40), 1),
                "curtailment_kwh": round(rng.uniform(0, 25), 1),
                "p2p_share": round(rng.uniform(0.2, 0.6), 3),
                "total_cost": round(rng.uniform(800, 1500), 0),
                "voltage_violations": rng.randint(0, 12),
                "losses_kwh": round(rng.uniform(10, 30), 1),
            },
            manifest={
                "network": "1-LV-semiurb4--0-sw",
                "reward.version": "corrected-v1",
                "data_status": "reconstructed-unverified",
                "commit": "demo",
            },
        )

    def training_curve(self, run_id: str) -> Series:
        """Sample-data version of ``ResultService.training_curve``."""
        rng = random.Random(run_id)
        it = list(range(0, 200, 5))
        train = [
            round(-40 + 55 * (1 - math.exp(-i / 60)) + rng.uniform(-3, 3), 2)
            for i in it
        ]
        ev = [round(v + rng.uniform(-2, 2), 2) for v in train]
        return Series(
            x=it,
            y={
                "train": train,
                "evaluation": ev,
                "no_order baseline": [-18.0] * len(it),
                "random baseline": [-9.0] * len(it),
            },
            x_label="iteration",
            y_label="episode return",
        )

    def step_records(self, run_id: str, episode: int = 0) -> list[dict]:
        """Sample-data version of ``ResultService.step_records``."""
        rng = random.Random(f"{run_id}-{episode}")
        return [
            {
                "step": t,
                "orders": 8,
                "p2p_trades": rng.randint(0, 6),
                "dso_trades": rng.randint(1, 8),
                "clearing_price": round(rng.uniform(80, 220), 1),
                "p2p_kwh": round(rng.uniform(0, 90), 1),
                "import_kwh": round(rng.uniform(-60, 120), 1),
                "min_v_pu": round(rng.uniform(0.93, 1.0), 3),
                "violations": rng.randint(0, 2),
            }
            for t in HOURS
        ]

    def grid_series(self, run_id: str, episode: int = 0) -> Series:
        """Sample-data version of ``ResultService.grid_series``."""
        vmin = [
            round(
                0.985
                - 0.04 * math.exp(-(((h - 19) / 2.5) ** 2))
                + 0.015 * math.exp(-(((h - 13) / 3) ** 2)),
                4,
            )
            for h in HOURS
        ]
        vmax = [
            round(1.01 + 0.035 * math.exp(-(((h - 13) / 3) ** 2)), 4) for h in HOURS
        ]
        load = [
            round(
                45
                + 35 * math.exp(-(((h - 19) / 3) ** 2))
                + 25 * math.exp(-(((h - 13) / 3) ** 2)),
                1,
            )
            for h in HOURS
        ]
        return Series(
            x=HOURS,
            y={
                "min voltage (pu)": vmin,
                "max voltage (pu)": vmax,
                "max line loading (%)": load,
            },
            x_label="hour",
            y_label="",
        )

    def agent_series(self, run_id: str, episode: int = 0) -> Series:
        """Sample-data version of ``ResultService.agent_series``."""
        return Series(
            x=HOURS,
            y={
                f"agent {i} SoC": [
                    round(0.5 + 0.35 * math.sin((h + 3 * i) / 24 * 2 * math.pi), 3)
                    for h in HOURS
                ]
                for i in range(4)
            },
            x_label="hour",
            y_label="state of charge",
        )

    def matrix(self, experiment_id: str, metric: str) -> MatrixTable:
        """Sample-data version of ``ResultService.matrix``."""
        rng = random.Random(f"{experiment_id}-{metric}")
        mean = [
            [round(rng.uniform(0.3, 0.9), 3) for _ in ALGORITHMS] for _ in PARADIGMS
        ]
        std = [
            [round(rng.uniform(0.01, 0.08), 3) for _ in ALGORITHMS] for _ in PARADIGMS
        ]
        return MatrixTable(
            metric=metric,
            rows=[p.upper() for p in PARADIGMS],
            columns=[a.upper() for a in ALGORITHMS],
            mean=mean,
            std=std,
        )

    def compare(self, run_ids: list[str], metric: str) -> Series:
        """Sample-data version of ``ResultService.compare``."""
        return Series(
            x=list(range(0, 200, 5)),
            y={r: self.training_curve(r).y["evaluation"] for r in run_ids},
            x_label="iteration",
            y_label=metric,
        )

    def export(self, run_ids: list[str], fmt: str = "csv") -> str:
        """Sample-data version of ``ResultService.export``."""
        return f"exports/{len(run_ids)}-runs.{fmt}"
