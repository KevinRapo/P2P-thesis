"""Plain data returned by application services.

These models are the only types that cross the boundary between the
application layer and its callers (NiceGUI Studio, CLI, notebooks). They must
stay free of MARLEM runtime objects, pandapower nets and Ray objects, see
docs_thesis/thesis/architecture/04-application-layer.md.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

# The experiment file and run records are defined in experiments/models/records.py.
# They are re-exported here on purpose: the Studio may only import application/
# (tests/test_studio_boundaries.py), so this module is its one source of data types.
from src_thesis.experiments.models.records import (  # noqa: F401
    ExperimentFile,
    ExperimentMeta,
    RunCell,
    RunState,
)

# --------------------------------------------------------------------------- experiment file


class FileSummary(BaseModel):
    """One row of the Library: a preset or one of your files.

    Attributes:
        id: File ID (the file name without ``.marlem.json``).
        name: ``meta.name``.
        kind: ``"preset"`` (read-only, in the repository) or ``"draft"`` (library).
        path: Where the file is.
        modified: Last change on disk.
        tags: ``meta.tags``.
        network: SimBench code or network name from ``grid.source``.
        participants: Number of participants.
        runs: Runs created from the file (0 until the real ExperimentService).
    """

    id: str
    name: str
    kind: Literal["preset", "draft", "file"]
    path: str
    modified: datetime
    tags: list[str] = Field(default_factory=list)
    network: str = ""
    participants: int = 0
    runs: int = 0


class FieldChange(BaseModel):
    """One difference found by ``ConfigService.diff``.

    Attributes:
        path: Dotted path, e.g. ``participants[2].bus``.
        before: Value in the first file; ``None`` if unset there.
        after: Value in the second file; ``None`` if unset there.
    """

    path: str
    before: Any = None
    after: Any = None


# --------------------------------------------------------------------------- grid catalogue


class NetworkSource(BaseModel):
    """Which network.

    Attributes:
        type: ``"simbench"``, ``"pandapower_builtin"`` or ``"pandapower_file"``.
        code: SimBench code, pandapower function name or file path.
    """

    type: Literal["simbench", "pandapower_builtin", "pandapower_file"]
    code: str


class NetworkInfo(BaseModel):
    """Catalog entry. Counts and flags are ``None`` until the network is loaded."""

    source: NetworkSource
    label: str
    voltage_level: str
    buses: int | None = None
    loads: int | None = None
    sgens: int | None = None
    storage: int | None = None
    has_profiles: bool | None = None
    has_line_ratings: bool | None = None
    has_geodata: bool | None = None


class NetworkSummary(BaseModel):
    """Totals of one network for the Grid page.

    Attributes:
        info: The catalog entry.
        total_load_kw: Sum of the loads' rated active power.
        total_generation_kw: Sum of the static generators' rated active power.
        lines: Number of lines.
        transformers: Number of transformers.
        profile_year: Year of the network's SimBench profiles; ``None`` without
            profiles.
    """

    info: NetworkInfo
    total_load_kw: float
    total_generation_kw: float
    lines: int
    transformers: int
    profile_year: int | None = None


class TopologyView(BaseModel):
    """Plain topology for plotting; no solver objects."""

    buses: list[dict[str, Any]]  # {"id", "x", "y", "kind", "vn_kv"}
    lines: list[dict[str, Any]]  # {"id", "from", "to", "kind", "closed"}
    external_grid_bus: str | None = None
    coordinates: Literal["geodata", "generated"] = "geodata"


class ElementInfo(BaseModel):
    """A load, static generator or storage unit.

    Attributes:
        id: Element name.
        element_type: ``"load"``, ``"sgen"`` or ``"storage"``.
        bus: Bus ID it is connected to.
        profile_type: SimBench profile name; empty if none.
        rated_kw: Rated active power.
    """

    id: str
    element_type: Literal["load", "sgen", "storage"]
    bus: str
    profile_type: str = ""
    rated_kw: float = 0.0


class PowerFlowPreview(BaseModel):
    """One power flow on the unmodified network (the Grid page's preview).

    Attributes:
        converged: Whether the power flow converged.
        min_voltage_pu: Lowest bus voltage.
        max_voltage_pu: Highest bus voltage.
        max_line_loading_percent: Highest line loading; ``None`` without line ratings.
        losses_kw: Total losses.
        bus_voltage_pu: Voltage per bus ID, for colouring the topology.
        violations: Limit violations as readable text.
        max_trafo_loading_percent: Highest transformer loading.
        external_grid_kw: Exchange with the upstream grid (+ import, − export).
        notes: Which profile values were used and which checks were switched off.
    """

    converged: bool
    min_voltage_pu: float | None
    max_voltage_pu: float | None
    max_line_loading_percent: float | None
    losses_kw: float | None
    bus_voltage_pu: dict[str, float]
    violations: list[str] = Field(default_factory=list)
    max_trafo_loading_percent: float | None = None
    external_grid_kw: float | None = None
    notes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- profiles


class ProfileType(BaseModel):
    """A profile that can be assigned to a participant (SimBench catalogue).

    Attributes:
        code: Profile name, e.g. ``"H0-B"`` (household) or ``"PV3"``.
        category: What kind of load or generation it describes.
        description: Readable explanation.
        table: SimBench profile table it comes from (``load``, ``renewables``, …).
        quantities: ``["p"]``, or ``["p", "q"]`` for loads.
        elements: Number of network elements that use it.
        mean: Mean active-power factor over the year (1.0 = rated power).
        peak: Highest active-power factor over the year.
    """

    code: str
    category: Literal[
        "household",
        "commercial",
        "agricultural",
        "pv",
        "wind",
        "biomass",
        "storage",
        "other",
    ]
    description: str = ""
    table: str = ""
    quantities: list[str] = Field(default_factory=lambda: ["p"])
    elements: int = 0
    mean: float | None = None
    peak: float | None = None


class Series(BaseModel):
    """Chart-ready series: one x axis, several named y lists."""

    x: list[Any]
    y: dict[str, list[float]]
    x_label: str = ""
    y_label: str = ""


# --------------------------------------------------------------------------- validation


class Severity(str, Enum):
    """How serious a validation finding is; errors block a launch."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Finding(BaseModel):
    """One validation finding.

    Attributes:
        code: Stable identifier, e.g. ``"GRID_MAPPING_DUPLICATE_OWNER"``.
        severity: Error, warning or info.
        area: Schema, data, grid mapping, time, protocol or resources.
        path: Dotted path of the field, so the Studio can jump to it.
        message: What is wrong.
        fix_hint: How to fix it.
    """

    code: str
    severity: Severity
    area: str
    path: str
    message: str
    fix_hint: str = ""


class ValidationReport(BaseModel):
    """All findings of one validation.

    Attributes:
        file_hash: Canonical hash of the validated file.
        level: ``"schema"``, ``"references"`` or ``"full"``.
        findings: The findings.
    """

    file_hash: str
    level: Literal["schema", "references", "full"]
    findings: list[Finding] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when there is no error (warnings are allowed)."""
        return not any(f.severity == Severity.ERROR for f in self.findings)


class DryRunResult(BaseModel):
    """Outcome of building the environment and taking one step.

    Attributes:
        ok: Whether the step succeeded.
        observation_dims: Observation size per agent.
        power_flow_converged: Whether the first power flow converged.
        settlement_residual_kwh: Energy-balance residual of the settlement (should be
            ~0).
        messages: What was checked and found.
    """

    ok: bool
    observation_dims: dict[str, int] = Field(default_factory=dict)
    power_flow_converged: bool | None = None
    settlement_residual_kwh: float | None = None
    messages: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- runs and results


class RunSummary(BaseModel):
    """One run in the Runs, Results and Compare lists.

    Attributes:
        run_id: The run's ID.
        experiment_id: The experiment file's ``meta.id``.
        cell: Algorithm, paradigm, seed and sweep point.
        network: Network code.
        state: Lifecycle state.
        progress: Share of the budget done (0..1).
        started: Start time.
        elapsed_s: Running time so far.
        eta_s: Estimated time left.
    """

    run_id: str
    experiment_id: str
    cell: RunCell
    network: str
    state: RunState
    progress: float = 0.0  # 0..1 of the budget
    started: datetime | None = None
    elapsed_s: float = 0.0
    eta_s: float | None = None


class RunStatus(BaseModel):
    """Live view of one run for the Runs page.

    Attributes:
        summary: The run.
        iteration: Current training iteration.
        last_metrics: Latest reported metrics.
        log_tail: Last lines of the worker log.
    """

    summary: RunSummary
    iteration: int = 0
    last_metrics: dict[str, float] = Field(default_factory=dict)
    log_tail: list[str] = Field(default_factory=list)


class RunEstimate(BaseModel):
    """Size and expected duration of an experiment before it starts.

    Attributes:
        runs: Number of runs.
        estimated_hours: Expected total time.
        note: How the estimate was made.
    """

    runs: int
    estimated_hours: float
    note: str = ""


class RunResult(BaseModel):
    """Research outcomes are kept apart from RL return on purpose."""

    run_id: str
    rl_return: float
    outcomes: dict[
        str, float
    ]  # served/unmet demand, curtailment, P2P share, violations, losses …
    manifest: dict[str, Any] = Field(default_factory=dict)


class MatrixTable(BaseModel):
    """Paradigm × algorithm table of one metric (the 3 × 3 result).

    Attributes:
        metric: The metric shown.
        rows: Paradigms.
        columns: Algorithms.
        mean: Mean over seeds; ``None`` where no run finished.
        std: Standard deviation over seeds.
    """

    metric: str
    rows: list[str]  # paradigms
    columns: list[str]  # algorithms
    mean: list[list[float | None]]
    std: list[list[float | None]]


class RepositoryHealth(BaseModel):
    """Repository and environment state for the Home page.

    Attributes:
        git_dirty: Whether there are uncommitted changes.
        validation_progress: Share of the validation issues closed.
        dependencies_ok: Whether the required packages are installed.
        messages: Details.
    """

    git_dirty: bool
    validation_progress: float  # share of validation-plan issues closed
    dependencies_ok: bool
    messages: list[str] = Field(default_factory=list)
