"""Technology-neutral grid contract (docs_thesis/thesis/architecture/01-simbench-grid.md §5).

Plain, frozen data only: no pandapower, SimBench or NetworkX objects cross this
seam. The pandapower adapter (``adapters/grid/simbench_new.py``) produces these
records; the market, the application services and the Studio consume them.

Status: the catalog and preview records are used by the Studio's Grid page
(phase R3). ``ParticipantInjection`` and ``GridModel`` are the step-time
contract for phase R4 and have no implementation yet.
"""

from dataclasses import dataclass, field
from typing import Literal, Mapping, Protocol, Sequence

SourceType = Literal["simbench", "pandapower_builtin", "pandapower_file"]


# --------------------------------------------------------------------- networks
@dataclass(frozen=True)
class NetworkRef:
    """Which network: a SimBench code, a pandapower built-in name or a file path."""

    source_type: SourceType
    code: str


@dataclass(frozen=True)
class NetworkInfo:
    """Catalog entry. Element counts are ``None`` until the network is loaded."""

    ref: NetworkRef
    label: str
    voltage_level: str
    buses: int | None = None
    loads: int | None = None
    sgens: int | None = None
    storage: int | None = None
    has_profiles: bool | None = None
    has_line_ratings: bool | None = None
    has_geodata: bool | None = None


@dataclass(frozen=True)
class NetworkSummary:
    info: NetworkInfo
    total_load_kw: float
    total_generation_kw: float
    lines: int
    transformers: int
    profile_year: int | None = None


@dataclass(frozen=True)
class BusView:
    id: str
    x: float
    y: float
    kind: str  # "external_grid", "load", "pv", "load+pv", "storage", "bus", ...
    vn_kv: float


@dataclass(frozen=True)
class BranchView:
    id: str
    from_bus: str
    to_bus: str
    kind: Literal["line", "trafo", "switch"]
    closed: bool = True


@dataclass(frozen=True)
class TopologyView:
    buses: tuple[BusView, ...]
    branches: tuple[BranchView, ...]
    external_grid_bus: str | None
    coordinates: Literal["geodata", "generated"] = "geodata"


@dataclass(frozen=True)
class ElementRecord:
    id: str
    element_type: Literal["load", "sgen", "storage"]
    bus: str
    profile_type: str = ""
    rated_kw: float = 0.0


# --------------------------------------------------------------------- step contract
@dataclass(frozen=True)
class ParticipantInjection:
    """Built from settlement, never from trades (01 §5)."""

    participant_id: str
    bus_id: str
    production_kw: float
    consumption_kw: float
    net_injection_kw: float


@dataclass(frozen=True)
class GridViolation:
    code: str  # "V_LOW", "V_HIGH", "LINE_OVERLOAD", "TRAFO_OVERLOAD", "NOT_CONVERGED"
    element_type: str
    element_id: str | None
    observed: float | None
    limit: float | None


@dataclass(frozen=True)
class GridAssessment:
    """Result of one power flow at one step."""

    step: int
    converged: bool
    min_voltage_pu: float | None
    max_voltage_pu: float | None
    max_line_loading_percent: float | None  # None if the network has no ratings
    max_trafo_loading_percent: float | None
    losses_kwh: float | None
    external_grid_kwh: float | None  # + import from upstream, − export
    bus_voltage_pu: Mapping[str, float]
    violations: tuple[GridViolation, ...]
    notes: tuple[str, ...] = field(default_factory=tuple)


class GridModel(Protocol):
    """Step-time grid used by the environment (phase R4)."""

    def reset(
        self, episode_seed: int | None = None, day: str | None = None
    ) -> None: ...

    def assess(
        self, step: int, injections: Sequence[ParticipantInjection]
    ) -> GridAssessment: ...

    def electrical_distance(self, bus_a: str, bus_b: str) -> float: ...

    def summary(self) -> NetworkSummary: ...

    def topology_view(self) -> TopologyView: ...
