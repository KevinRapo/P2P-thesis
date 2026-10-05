"""ResultService: reading runs (04 §5).

Simulation runs are read from their folders: ``raw/steps.jsonl`` (also while the
run is still going: a half-written last line is ignored), ``metrics/*.jsonl`` and
``grid_topology.json``. Training curves, the paradigm × algorithm matrix and run
comparison still return generated sample data.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any

from src_thesis.marlem.simulation.checks import CATALOG as CHECKS
from src_thesis.platform.kernel.store.filesystem import ExperimentStore
from src_thesis.platform.services.experiment_service import ALGORITHMS, PARADIGMS
from src_thesis.platform.services.models import (
    CheckResult,
    MatrixTable,
    ReplayTopology,
    RunResult,
    Series,
    TopologyView,
)
from src_thesis.platform.services.workspace import Workspace

HOURS = list(range(24))  # sample curves cover one day


class ResultService:
    """Reading runs: outcomes, replays, checks, comparisons.

    Args:
        workspace: Where the store lives; the default workspace when ``None``.
    """

    SAMPLE_DATA = True  # training curves, the matrix and comparison are samples

    def __init__(self, workspace: Workspace | None = None) -> None:
        self.workspace = workspace or Workspace.default()
        self.store = ExperimentStore(self.workspace.store)

    # ------------------------------------------------------------------ simulation
    def replay(self, run_id: str) -> list[dict[str, Any]]:
        """Every recorded step of a run, in order (all days).

        Each record has ``day``, ``step``, ``orders``, ``trades``, ``settlement``
        (per agent), ``assessment`` (the power flow), ``kpis`` (prices) and
        ``checks`` (findings). A run that is still going returns what it has so
        far.
        """
        path = self.store.run_dir(run_id) / "raw" / "steps.jsonl"
        out: list[dict[str, Any]] = []
        if not path.exists():
            return out
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:  # the line being written right now
                    break
        return out

    def topology(self, run_id: str) -> ReplayTopology | None:
        """The run's network and where its participants sit; ``None`` until the
        run has started."""
        path = self.store.run_dir(run_id) / "grid_topology.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        shape = data["topology"]
        return ReplayTopology(
            topology=TopologyView(
                buses=shape["buses"],
                lines=[
                    {
                        "id": b["id"],
                        "from": b["from_bus"],
                        "to": b["to_bus"],
                        "kind": b["kind"],
                        "closed": b["closed"],
                    }
                    for b in shape["branches"]
                ],
                external_grid_bus=shape["external_grid_bus"],
                coordinates=shape["coordinates"],
            ),
            participants={p["id"]: p["bus"] for p in data["participants"]},
            step_hours=data["step_hours"],
        )

    def checks(self, run_id: str) -> list[CheckResult]:
        """Every check with its failures over the run, in catalogue order.

        Computed from the recorded steps, so it is right while the run is going.
        """
        failures = {c: 0 for c in CHECKS}
        first: dict[str, tuple[str, int | None]] = {}
        for record in self.replay(run_id):
            for finding in record.get("checks", []):
                check = finding["check"]
                failures[check] += 1
                first.setdefault(check, (record["day"], record["step"]))
        for line in self.store.read_jsonl(run_id, "metrics/checks.jsonl"):
            for finding in line["findings"]:
                if finding["step"] is None:  # day-level findings are not in the steps
                    failures[finding["check"]] += 1
                    first.setdefault(finding["check"], (line["day"], None))
        return [
            CheckResult(
                id=info.id,
                title=info.title,
                severity=info.severity,
                issue=info.issue,
                explanation=info.explanation,
                failures=failures[info.id],
                first_step=first[info.id][1] if info.id in first else None,
                first_day=first[info.id][0] if info.id in first else None,
            )
            for info in CHECKS.values()
        ]

    def summary(self, run_id: str) -> RunResult:
        """Outcomes and manifest of one run.

        For simulation runs the outcomes are the totals over all days: energy
        traded with other participants and with the DSO, voltage extremes, grid
        violations and failed checks.
        """
        manifest = self.store.read_manifest(run_id)
        rows = list(self.store.read_jsonl(run_id, "metrics/summary.jsonl"))
        outcomes: dict[str, float] = {}
        if rows:
            low = [r["min_voltage_pu"] for r in rows if r["min_voltage_pu"] is not None]
            high = [
                r["max_voltage_pu"] for r in rows if r["max_voltage_pu"] is not None
            ]
            outcomes = {
                "steps_played": float(sum(r["steps_played"] for r in rows)),
                "trades": float(sum(r["trades"] for r in rows)),
                "p2p_kwh": round(sum(r["p2p_kwh"] for r in rows), 3),
                "dso_kwh": round(sum(r["dso_kwh"] for r in rows), 3),
                "grid_violations": float(sum(r["grid_violations"] for r in rows)),
                "not_converged": float(sum(r["not_converged"] for r in rows)),
                "failed_invariants": float(sum(r["failed_invariants"] for r in rows)),
            }
            if low:
                outcomes["min_voltage_pu"] = min(low)
            if high:
                outcomes["max_voltage_pu"] = max(high)
        resolved = self.store.read_resolved(run_id)
        source = resolved.grid.source
        return RunResult(
            run_id=run_id,
            rl_return=None,
            outcomes=outcomes,
            manifest={
                "network": source.code if source else "",
                "controller": manifest.cell.algorithm,
                "kind": manifest.cell.kind,
                "days": manifest.days,
                "data_status": resolved.meta.data_status or "",
                "commit": manifest.code.get("commit", "") if manifest.code else "",
            },
        )

    def step_records(self, run_id: str, episode: int = 0) -> list[dict]:
        """One summary row per step of one day (``episode`` = day index).

        Rows: ``step``, ``orders``, ``p2p_trades``, ``dso_trades``,
        ``clearing_price``, ``p2p_kwh``, ``import_kwh`` (+ from upstream),
        ``min_v_pu`` and ``violations``.
        """
        days = sorted({r["day"] for r in self.replay(run_id)})
        if episode >= len(days):
            return []
        rows = []
        for r in self.replay(run_id):
            if r["day"] != days[episode]:
                continue
            trades = r["trades"]
            dso = [t for t in trades if "DSO" in (t["buyer_id"], t["seller_id"])]
            assessment = r.get("assessment") or {}
            rows.append(
                {
                    "step": r["step"],
                    "orders": len(r["orders"]),
                    "p2p_trades": len(trades) - len(dso),
                    "dso_trades": len(dso),
                    "clearing_price": r["kpis"].get("clearing", 0.0),
                    "p2p_kwh": round(
                        sum(t["quantity_kwh"] for t in trades if t not in dso), 3
                    ),
                    "import_kwh": assessment.get("external_grid_kwh"),
                    "min_v_pu": assessment.get("min_voltage_pu"),
                    "violations": len(assessment.get("violations", [])),
                }
            )
        return rows

    def grid_series(self, run_id: str, episode: int = 0) -> Series:
        """Voltages, loading and losses over one day of a simulation run."""
        rows = [
            r for r in self.replay(run_id) if r["day"] == self._day(run_id, episode)
        ]
        a = [r.get("assessment") or {} for r in rows]
        return Series(
            x=[r["step"] for r in rows],
            y={
                "min voltage (pu)": [x.get("min_voltage_pu") or math.nan for x in a],
                "max voltage (pu)": [x.get("max_voltage_pu") or math.nan for x in a],
                "max line loading (%)": [
                    x.get("max_line_loading_percent") or 0.0 for x in a
                ],
            },
            x_label="step",
            y_label="",
        )

    def agent_series(self, run_id: str, episode: int = 0) -> Series:
        """Battery energy and net physical injection of each agent over one day."""
        rows = [
            r for r in self.replay(run_id) if r["day"] == self._day(run_id, episode)
        ]
        y: dict[str, list[float]] = {}
        for r in rows:
            for agent, s in r["settlement"].items():
                if s.get("soc_kwh") is not None:
                    y.setdefault(f"{agent} battery (kWh)", []).append(s["soc_kwh"])
                y.setdefault(f"{agent} net (kWh)", []).append(
                    s["production_kwh"] - s["consumption_kwh"]
                )
        return Series(x=[r["step"] for r in rows], y=y, x_label="step", y_label="kWh")

    def _day(self, run_id: str, episode: int) -> str | None:
        days = sorted({r["day"] for r in self.replay(run_id)})
        return days[episode] if episode < len(days) else None

    # ------------------------------------------------------------------ samples
    def training_curve(self, run_id: str) -> Series:
        """Training and evaluation return per iteration (sample data for now)."""
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

    def matrix(self, experiment_id: str, metric: str) -> MatrixTable:
        """Paradigm × algorithm table of ``metric`` (sample data for now)."""
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
        """One metric of several runs, for overlaying (sample data for now)."""
        return Series(
            x=list(range(0, 200, 5)),
            y={r: self.training_curve(r).y["evaluation"] for r in run_ids},
            x_label="iteration",
            y_label=metric,
        )

    def export(self, run_ids: list[str], fmt: str = "csv") -> str:
        """Write the runs' step summaries to ``<workspace>/exports``.

        Args:
            run_ids: Runs to export.
            fmt: ``"csv"`` or ``"json"``.

        Returns:
            The path written.
        """
        folder = self.workspace.exports
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{len(run_ids)}-runs.{fmt}"
        rows = [{"run_id": r, **row} for r in run_ids for row in self.step_records(r)]
        if fmt == "json":
            path.write_text(json.dumps(rows, indent=1), encoding="utf-8")
        else:
            import csv

            with open(path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else [])
                writer.writeheader()
                writer.writerows(rows)
        return str(Path(path))
