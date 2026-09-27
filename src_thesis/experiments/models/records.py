"""Records of the experiment layer (06-experiment-layer.md §2).

The experiment file (03) and everything the system writes about a run: the cell
it runs, its manifest, its status and its artifact index. Plain Pydantic models
only, so the application layer and the worker can share them without loading
MARLEM, pandapower or Ray.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- file
class ExperimentMeta(BaseModel):
    id: str
    name: str
    description: str = ""
    author: str = ""
    tags: list[str] = Field(default_factory=list)
    derived_from: str | None = None
    data_status: Literal["synthetic", "measured", "reconstructed-unverified"] = (
        "synthetic"
    )


class ExperimentFile(BaseModel):
    """One study, see docs/thesis/architecture/03-experiment-config.md.

    The sections are dictionaries for now; each becomes a typed model when its
    Studio page and validation rules are implemented.
    """

    schema_version: str = SCHEMA_VERSION
    kind: Literal["marlem-experiment"] = "marlem-experiment"
    meta: ExperimentMeta
    time: dict[str, Any] = Field(default_factory=dict)
    grid: dict[str, Any] = Field(default_factory=dict)
    participants: list[dict[str, Any]] = Field(default_factory=list)
    market: dict[str, Any] = Field(default_factory=dict)
    dso: dict[str, Any] = Field(default_factory=dict)
    environment: dict[str, Any] = Field(default_factory=dict)
    learning: dict[str, Any] = Field(default_factory=dict)
    evaluation: dict[str, Any] = Field(default_factory=dict)
    baselines: list[Any] = Field(default_factory=list)
    sweep: dict[str, Any] = Field(default_factory=dict)
    resources: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- runs
class RunCell(BaseModel):
    """One run of an experiment: a sweep point, a learner or baseline, a seed.

    ``kind`` selects the runner: ``train`` (algorithm × paradigm), ``baseline``
    (``algorithm`` holds the baseline name, ``paradigm`` is ``"-"``) or ``noop``
    (a smoke run for tests; never produced by ``expand``).
    """

    kind: Literal["train", "baseline", "noop"] = "train"
    sweep_label: str = ""
    sweep_point: dict[str, Any] = Field(default_factory=dict)
    algorithm: str
    paradigm: str
    seed: int


class RunState(str, Enum):
    READY = "READY"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"


TERMINAL_STATES = frozenset({RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED})

# Allowed state changes (04 §4). Anything may fail; a terminal state is final.
TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    # READY -> RUNNING: a worker started directly (CLI debugging) skips the queue
    RunState.READY: frozenset({RunState.QUEUED, RunState.RUNNING, RunState.CANCELLED}),
    RunState.QUEUED: frozenset({RunState.RUNNING, RunState.CANCELLED}),
    RunState.RUNNING: frozenset(
        {RunState.COMPLETED, RunState.CANCELLING, RunState.CANCELLED}
    ),
    RunState.CANCELLING: frozenset({RunState.CANCELLED, RunState.COMPLETED}),
    RunState.COMPLETED: frozenset(),
    RunState.FAILED: frozenset(),
    RunState.CANCELLED: frozenset(),
}


def can_transition(old: RunState, new: RunState) -> bool:
    if old in TERMINAL_STATES:
        return False
    return new == RunState.FAILED or new in TRANSITIONS[old]


class Manifest(BaseModel):
    """Written once, before the run starts; never changed afterwards (03 §5)."""

    run_id: str
    experiment_id: str
    cell: RunCell
    created: datetime = Field(default_factory=utc_now)
    file_hash: str  # canonical hash of the user's file
    resolved_hash: str  # canonical hash of resolved.json; the worker checks it
    code: dict[str, Any] = Field(default_factory=dict)  # git commit, dirty diff hash
    environment: dict[str, Any] = Field(default_factory=dict)  # python, packages
    data: dict[str, Any] = Field(default_factory=dict)  # network, CSV sha256
    days: dict[str, list[str]] = Field(default_factory=dict)  # train, eval
    time_alignment: str = ""
    validation_hash: str | None = None
    platform: dict[str, Any] = Field(default_factory=dict)


class StatusRecord(BaseModel):
    """``status.json``: the live state of one run, rewritten atomically."""

    run_id: str
    experiment_id: str
    state: RunState = RunState.READY
    pid: int | None = None
    created: datetime = Field(default_factory=utc_now)
    started: datetime | None = None
    updated: datetime = Field(default_factory=utc_now)
    finished: datetime | None = None
    progress: float = 0.0  # 0..1 of the budget
    iteration: int = 0
    last_metrics: dict[str, float] = Field(default_factory=dict)
    message: str = ""


class ArtifactIndex(BaseModel):
    """``artifacts.json``: what the run produced, by name, relative to its folder."""

    files: dict[str, str] = Field(default_factory=dict)
