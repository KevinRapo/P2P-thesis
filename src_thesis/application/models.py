"""Plain data returned by application services.

These models are the only types that cross the boundary between the
application layer and its callers (NiceGUI Studio, CLI, notebooks). They must
stay free of MARLEM runtime objects, pandapower nets and Ray objects, see
docs/thesis/architecture/04-services.md.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- experiment file


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

    The sections are kept as dictionaries in this scaffold; each becomes a
    typed model when its page and validation rules are implemented.
    """

    schema_version: str = "1.0"
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


class FileSummary(BaseModel):
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
    path: str
    before: Any = None
    after: Any = None


class RunCell(BaseModel):
    sweep_label: str = ""
    algorithm: str
    paradigm: str
    seed: int


# --------------------------------------------------------------------------- grid catalogue


class NetworkSource(BaseModel):
    type: Literal["simbench", "pandapower_builtin", "pandapower_file"]
    code: str


class NetworkInfo(BaseModel):
    source: NetworkSource
    label: str
    voltage_level: str
    buses: int
    loads: int
    sgens: int
    storage: int
    has_profiles: bool
    has_line_ratings: bool
    has_geodata: bool


class NetworkSummary(BaseModel):
    info: NetworkInfo
    total_load_kw: float
    total_generation_kw: float
    lines: int
    transformers: int


class TopologyView(BaseModel):
    """Plain topology for plotting; no solver objects."""

    buses: list[dict[str, Any]]  # {"id", "x", "y", "kind"}
    lines: list[dict[str, Any]]  # {"id", "from", "to"}
    external_grid_bus: str | None = None


class ElementInfo(BaseModel):
    id: str
    element_type: Literal["load", "sgen", "storage"]
    bus: str
    profile_type: str = ""
    rated_kw: float = 0.0


class PowerFlowPreview(BaseModel):
    converged: bool
    min_voltage_pu: float | None
    max_voltage_pu: float | None
    max_line_loading_percent: float | None
    losses_kw: float | None
    bus_voltage_pu: dict[str, float]
    violations: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- profiles


class ProfileType(BaseModel):
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


class Series(BaseModel):
    """Chart-ready series: one x axis, several named y lists."""

    x: list[Any]
    y: dict[str, list[float]]
    x_label: str = ""
    y_label: str = ""


# --------------------------------------------------------------------------- validation


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Finding(BaseModel):
    code: str
    severity: Severity
    area: str
    path: str
    message: str
    fix_hint: str = ""


class ValidationReport(BaseModel):
    file_hash: str
    level: Literal["schema", "references", "full"]
    findings: list[Finding] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.severity == Severity.ERROR for f in self.findings)


class DryRunResult(BaseModel):
    ok: bool
    observation_dims: dict[str, int] = Field(default_factory=dict)
    power_flow_converged: bool | None = None
    settlement_residual_kwh: float | None = None
    messages: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- runs and results


class RunState(str, Enum):
    READY = "READY"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"


class RunSummary(BaseModel):
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
    summary: RunSummary
    iteration: int = 0
    last_metrics: dict[str, float] = Field(default_factory=dict)
    log_tail: list[str] = Field(default_factory=list)


class RunEstimate(BaseModel):
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
    metric: str
    rows: list[str]  # paradigms
    columns: list[str]  # algorithms
    mean: list[list[float | None]]
    std: list[list[float | None]]


class RepositoryHealth(BaseModel):
    git_dirty: bool
    validation_progress: float  # share of validation-plan issues closed
    dependencies_ok: bool
    messages: list[str] = Field(default_factory=list)
