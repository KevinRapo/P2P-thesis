"""Plain data returned by application services.

These models are the only types that cross the boundary between the
application layer and its callers (NiceGUI Studio, CLI, notebooks). They must
stay free of MARLEM runtime objects, pandapower nets and Ray objects, see
docs/thesis/architecture/03-application-layer.md.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

# The experiment file and run records belong to the experiment layer (architecture README §2.1);
# they are re-exported here so callers keep importing them from one place.
from src_thesis.experiments.models import (  # noqa: F401
    ExperimentFile,
    ExperimentMeta,
    RunCell,
    RunState,
)

# --------------------------------------------------------------------------- experiment file


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


# --------------------------------------------------------------------------- grid catalogue


class NetworkSource(BaseModel):
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
    max_trafo_loading_percent: float | None = None
    external_grid_kw: float | None = None
    notes: list[str] = Field(default_factory=list)


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
