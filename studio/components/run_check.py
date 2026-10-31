"""An experiment and a target as the Runs and Experiments pages and the Summary show
them: what ``check`` found, and what an experiment makes."""

from __future__ import annotations

from typing import Optional

from nicegui import run, ui

from studio.adapters.run_service import RunService


def fail(message: str) -> None:
    """The error of an action the user asked for: a notification that stays until it
    is closed."""
    ui.notify(message, type="negative", multi_line=True, close_button=True)


# --------------------------------------------------------------------------------------
# What ``check`` found
# --------------------------------------------------------------------------------------
async def read_check(
    service: RunService, target: str, spec_path: Optional[str]
) -> dict:
    """``service.check`` in a worker thread. A target that cannot even be made
    (incomplete ``targets.toml``) is a report that is not ok, with the reason."""
    try:
        return await run.io_bound(service.check_target, target, spec_path)
    except (OSError, RuntimeError, ValueError) as error:
        return {
            "ok": False,
            "problems": [str(error)],
            "local_commit": None,
            "cluster_commit": None,
            "active": None,
        }


def _short(commit: Optional[str]) -> str:
    return commit[:8] if commit else "unknown"


def show_report(report: dict) -> None:
    """A report of ``check`` in the current container: Ready, or the problems that
    stop a start; the two commits; and the experiments that are queued or running, as
    a reminder not to update the cluster's checkout while they are."""
    # Icon | "Ready" or the list of problems
    with ui.row().classes("items-start gap-2 no-wrap"):
        if report["ok"]:
            ui.icon("check_circle", size="20px", color="positive")
            ui.label("Ready").classes("text-body2")
        else:
            ui.icon("warning", size="20px", color="orange-8")
            with ui.column().classes("gap-0"):
                for problem in report["problems"]:
                    ui.label(problem).classes("text-body2")

    cluster, local = report["cluster_commit"], report["local_commit"]
    ui.label(f"cluster {_short(cluster)} · this PC {_short(local)}").classes("mls-mono")

    if report["active"]:
        ui.label(
            f"Queued or running: {', '.join(report['active'])}. Do not update or edit "
            "the cluster's checkout while they run."
        ).classes("mls-card-caption")


# --------------------------------------------------------------------------------------
# What an experiment makes
# --------------------------------------------------------------------------------------
def _budget(budget: int | dict) -> str:
    """The environment steps of each run: one number, or one per algorithm."""
    if isinstance(budget, dict):
        steps = ", ".join(f"{algorithm} {n:,}" for algorithm, n in budget.items())
    else:
        steps = f"{budget:,}"
    return f"{steps} env steps"


def _resources(resources: dict) -> str:
    text = (
        f"{resources['cpus']} cpus, {resources['mem_gb']:g} GB, "
        f"{resources['minutes']} min"
    )
    return f"{text}, node {resources['node']}" if resources.get("node") else text


def experiment_facts(record: dict) -> dict:
    """The name, runs, budget and resources of ``RunService.describe``'s record."""
    return {
        "Starts as": record["name"],
        "Runs": str(record["runs"]),
        "Budget per run": _budget(record["budget"]),
        "Cluster resources per run": _resources(record["resources"]),
    }
