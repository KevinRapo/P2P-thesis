"""Records of the experiment layer.

Why: every other module passes these around, so they are defined once, as Pydantic
models that validate themselves. The split matters: what the user writes
(``ExperimentFile``), what the system fixes once per run (``Manifest``) and what keeps
changing while it runs (``StatusRecord``) are separate records, so the fixed parts can
never be overwritten by a running worker.

The experiment file (02) and everything the system writes about a run: the cell
it runs, its manifest, its status and its artifact index. Plain Pydantic models
only, so the application layer and the worker can share them without loading
MARLEM, pandapower or Ray.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src_thesis.platform.kernel.models.sections import (
    Baseline,
    DsoSection,
    EnvironmentSection,
    EvaluationSection,
    GridSection,
    LearningSection,
    MarketSection,
    OutputsSection,
    Participant,
    ResourcesSection,
    SweepSection,
    TimeSection,
)

SCHEMA_VERSION = "1.0"


def utc_now() -> datetime:
    """Current time in UTC, timezone-aware; every record uses it."""
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- file
class ExperimentMeta(BaseModel):
    """The ``meta`` section: what the study is and where it came from (02 §3.1).

    Attributes:
        id: Stable identifier; the file name and the start of every run ID.
        name: Readable name.
        description: What the study does, and its deviations from the paper.
        author: Who wrote it.
        tags: Free labels, e.g. ``["paper", "case6"]``.
        derived_from: The preset (``preset:<id>``) or file it was copied from.
        data_status: Whether the data is synthetic, measured or reconstructed and
            unverified.
    """

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
    """One study, see docs_thesis/thesis/architecture/02-experiment-config.md.

    Every section is a typed model (``sections.py``). Write the file with
    ``to_data``: it keeps only what is set, so defaults stay out of the file and
    are applied when a run is resolved.
    """

    schema_version: str = SCHEMA_VERSION
    kind: Literal["marlem-experiment"] = "marlem-experiment"
    meta: ExperimentMeta
    time: TimeSection = Field(default_factory=TimeSection)
    grid: GridSection = Field(default_factory=GridSection)
    participants: list[Participant] = Field(default_factory=list)
    market: MarketSection = Field(default_factory=MarketSection)
    dso: DsoSection = Field(default_factory=DsoSection)
    environment: EnvironmentSection = Field(default_factory=EnvironmentSection)
    learning: LearningSection = Field(default_factory=LearningSection)
    evaluation: EvaluationSection = Field(default_factory=EvaluationSection)
    baselines: list[Baseline] = Field(default_factory=list)
    sweep: SweepSection = Field(default_factory=SweepSection)
    resources: ResourcesSection = Field(default_factory=ResourcesSection)
    outputs: OutputsSection = Field(default_factory=OutputsSection)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _sections_always_written(self) -> ExperimentFile:
        """Top-level sections and ``meta`` are written even when empty."""
        self.__pydantic_fields_set__.update(type(self).model_fields)
        self.meta.__pydantic_fields_set__.update(type(self.meta).model_fields)
        return self

    def to_data(self) -> dict[str, Any]:
        """The file as JSON-ready data: every section, inside them only what is set."""
        return self.model_dump(mode="json", exclude_unset=True)


# --------------------------------------------------------------------------- runs
class RunCell(BaseModel):
    """One run of an experiment: a sweep point, a learner or baseline, a seed.

    ``kind`` selects the runner: ``train`` (algorithm × paradigm), ``baseline``
    (``algorithm`` holds the baseline name, ``paradigm`` is ``"-"``), ``simulate``
    (``algorithm`` holds the scripted controller, ``paradigm`` is ``"-"``; made
    by the Simulate page, never by ``expand``) or ``noop`` (a smoke run for tests;
    never produced by ``expand``).

    A ``simulate`` run plays ``days`` consecutive days from ``day`` (the start of
    the file's time window when ``None``) with the controller's parameters.
    """

    kind: Literal["train", "baseline", "simulate", "noop"] = "train"
    sweep_label: str = ""
    sweep_point: dict[str, Any] = Field(default_factory=dict)
    algorithm: str
    paradigm: str
    seed: int
    controller_params: dict[str, float] = Field(default_factory=dict)
    day: str | None = None
    days: int = 1


class RunState(str, Enum):
    """Lifecycle state of a run (03 §5); ``TRANSITIONS`` lists the allowed moves."""

    READY = "READY"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"


TERMINAL_STATES = frozenset({RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED})

# Allowed state changes (03 §5). Anything may fail; a terminal state is final.
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
    """Whether a run may move from ``old`` to ``new`` (03 §5)."""
    if old in TERMINAL_STATES:
        return False
    return new == RunState.FAILED or new in TRANSITIONS[old]


class Manifest(BaseModel):
    """Written once, before the run starts; never changed afterwards (02 §5)."""

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
