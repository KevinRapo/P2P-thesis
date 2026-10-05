"""Simulation runs: scripted controllers play days on the file's market and network.

A ``simulate`` run (``RunCell.kind``) builds the market and the step-time grid from
the resolved file once per day, lets the controller named in ``cell.algorithm``
act, and writes what happened into the run folder while it happens:

- ``raw/steps.jsonl``: one line per step (orders, trades, settlement, grid
  assessment, prices, findings), flushed at once so the Studio can replay a run
  that is still going;
- ``metrics/checks.jsonl``: per day, every check with its failure count and the
  findings;
- ``metrics/summary.jsonl``: per day, the totals;
- ``grid_topology.json``: the network's buses and branches and where the
  participants sit, for drawing the replay.

No Ray, no training: the heavy imports happen when the run starts.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, timedelta

from src_thesis.platform.experiments.models.records import RunState
from src_thesis.platform.experiments.store.recorder import StepRecord
from src_thesis.platform.experiments.worker.runner import RunContext, RunOutcome


def day_list(first: str, days: int) -> list[str]:
    """``days`` consecutive dates starting at ``first`` (``YYYY-MM-DD``)."""
    start = date.fromisoformat(first)
    return [(start + timedelta(days=i)).isoformat() for i in range(days)]


class SimulateRunner:
    """Plays the cell's days with the cell's controller."""

    def run(self, ctx: RunContext) -> RunOutcome:
        """Simulate; ends CANCELLED if a cancel was requested between steps."""
        from src_thesis.marlem.environment.build import build_engine
        from src_thesis.marlem.environment.simulation import run_simulation
        from src_thesis.marlem.policies.registry import get_policy
        from src_thesis.platform.experiments.factory.environment import (
            build_engine_spec,
            build_grid,
            build_grid_view,
        )
        from src_thesis.platform.experiments.factory.profiles import window_start

        cell = ctx.cell
        resolved = ctx.resolved
        first = cell.day or window_start(resolved)
        days = day_list(first, max(1, cell.days))
        policy = get_policy(cell.algorithm, **cell.controller_params)
        recorder = ctx.recorder()
        recorder.flush_each_step = True
        recorder.mode = "all"
        done = 0
        findings = 0
        total = None
        for index, day in enumerate(days):
            spec = build_engine_spec(resolved, day, cell.seed + index)
            total = total or spec.steps * len(days)
            engine = build_engine(spec, build_grid_view(resolved, spec))
            grid = build_grid(resolved, spec)
            if index == 0:
                self._write_topology(ctx, grid, spec)
            recorder.start_episode(index, day, evaluation=True)

            def on_step(record, index=index, day=day) -> None:
                nonlocal done
                recorder.record(
                    StepRecord(
                        episode=index,
                        step=record["step"],
                        day=day,
                        orders=record["orders"],
                        trades=record["trades"],
                        settlement=record["settlement"],
                        assessment=record["assessment"] or {},
                        kpis=record["prices"],
                        checks=record["findings"],
                    )
                )
                done += 1
                low = (record["assessment"] or {}).get("min_voltage_pu")
                ctx.report(
                    done / total,
                    done,
                    {} if low is None else {"min_voltage_pu": low},
                )

            ctx.log(f"day {day}: {spec.steps} steps, seed {spec.seed}")
            for warning in spec.warnings:
                ctx.log(f"warning: {warning}")
            result = run_simulation(
                engine,
                spec,
                policy,
                grid,
                spec.seed,
                on_step=on_step,
                should_stop=ctx.should_stop,
            )
            recorder.end_episode({})
            findings += len(result.findings)
            ctx.store.append_jsonl(
                ctx.run_id,
                "metrics/checks.jsonl",
                {
                    "day": day,
                    "checks": result.checks,
                    "findings": [asdict(f) for f in result.findings],
                },
            )
            ctx.store.append_jsonl(
                ctx.run_id,
                "metrics/summary.jsonl",
                {"day": day, **result.summary, "warnings": result.warnings},
            )
            if result.stopped:
                return RunOutcome(
                    RunState.CANCELLED,
                    f"cancelled on {day} after {len(result.steps)} steps",
                    self._artifacts(),
                )
        return RunOutcome(
            RunState.COMPLETED,
            f"{len(days)} day(s), {done} steps, {findings} finding(s)",
            self._artifacts(),
        )

    @staticmethod
    def _artifacts() -> dict[str, str]:
        return {"grid_topology": "grid_topology.json"}

    @staticmethod
    def _write_topology(ctx: RunContext, grid, spec) -> None:
        """The network's shape and the participants' places, for the replay."""
        shape = grid.topology_view()
        data = {
            "topology": asdict(shape),
            "participants": [{"id": a.id, "bus": a.bus} for a in spec.agents],
            "step_hours": spec.step_hours,
        }
        path = ctx.store.run_dir(ctx.run_id) / "grid_topology.json"
        path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
