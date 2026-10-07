"""Technology-neutral grid contract: what crosses the grid seam.

Plain, frozen data only: no pandapower, SimBench or NetworkX objects cross this
seam. The pandapower adapter (``grid/simbench.py``) produces these records; the
market, the services and the Studio consume them.

The catalog records are used by the Studio's Inspect page. ``ParticipantInjection``
and ``GridModel`` are the step-time contract and have no implementation yet.
"""

from dataclasses import dataclass, field
from typing import Literal, Mapping, Protocol, Sequence

SourceType = Literal["simbench", "pandapower_builtin", "pandapower_file"]


# --------------------------------------------------------------------------------------
# Networks: catalog, topology, elements, profiles
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class NetworkRef:
    """Which network: a SimBench code, a pandapower built-in name or a file path."""

    source_type: SourceType
    code: str


@dataclass(frozen=True)
class NetworkInfo:
    """Catalog entry. Element counts are ``None`` until the network is loaded.

    ``category``, ``scenario`` and ``switches`` come from a SimBench code and are
    ``None`` for other sources.
    """

    ref: NetworkRef
    label: str
    voltage_level: str
    category: str | None = None
    scenario: int | None = None
    switches: bool | None = None
    buses: int | None = None
    loads: int | None = None
    sgens: int | None = None
    storage: int | None = None
    has_profiles: bool | None = None
    has_line_ratings: bool | None = None
    has_geodata: bool | None = None


@dataclass(frozen=True)
class NetworkSummary:
    """Totals of one network.

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


@dataclass(frozen=True)
class BusView:
    """A bus in the topology view.

    Attributes:
        id: Stable bus ID (the bus name when names are unique).
        x: Horizontal coordinate (geodata or generated layout).
        y: Vertical coordinate.
        kind: What is connected: external_grid, load, pv, load+pv, storage or bus.
        vn_kv: Nominal voltage.
    """

    id: str
    x: float
    y: float
    kind: str  # "external_grid", "load", "pv", "load+pv", "storage", "bus", ...
    vn_kv: float


@dataclass(frozen=True)
class BranchView:
    """A line, transformer or bus-to-bus switch.

    Attributes:
        id: Branch name.
        from_bus: Bus ID at one end (the high-voltage side for transformers).
        to_bus: Bus ID at the other end.
        kind: ``"line"``, ``"trafo"`` or ``"switch"``.
        closed: False if out of service or open.
    """

    id: str
    from_bus: str
    to_bus: str
    kind: Literal["line", "trafo", "switch"]
    closed: bool = True


@dataclass(frozen=True)
class TopologyView:
    """The network's shape for plotting; no pandapower objects.

    Attributes:
        buses: All buses.
        branches: All lines, transformers and bus-to-bus switches.
        external_grid_bus: Bus of the connection to the upstream grid.
        coordinates: Whether x/y come from the network's geodata or a generated layout.
    """

    buses: tuple[BusView, ...]
    branches: tuple[BranchView, ...]
    external_grid_bus: str | None
    coordinates: Literal["geodata", "generated"] = "geodata"


@dataclass(frozen=True)
class ElementRecord:
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


@dataclass(frozen=True)
class ProfileRecord:
    """One SimBench profile of a network: a normalised yearly time series.

    Values are factors of an element's rated power (1.0 = rated power), one row per
    15 minutes of the profile year.

    Attributes:
        name: Profile name, e.g. ``"H0-A"`` (household) or ``"PV5"``.
        table: SimBench profile table: ``"load"``, ``"renewables"``,
            ``"powerplants"`` or ``"storage"``.
        quantities: ``("p",)``, or ``("p", "q")`` for loads (active and reactive).
        elements: Number of network elements that use this profile.
        mean: Mean active-power factor over the year.
        peak: Highest active-power factor over the year.
    """

    name: str
    table: str
    quantities: tuple[str, ...]
    elements: int
    mean: float
    peak: float


# --------------------------------------------------------------------------------------
# Step: what one power flow takes and gives
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class GridLimits:
    """Limits that replace the network's own where set (``grid.limits``).

    Attributes:
        v_min_pu: Lowest voltage; each bus's own limit when ``None``.
        v_max_pu: Highest voltage; each bus's own limit when ``None``.
        line_max_percent: Line loading limit; the line's own when ``None``.
        trafo_max_percent: Transformer loading limit; 100 when ``None``.
    """

    v_min_pu: float | None = None
    v_max_pu: float | None = None
    line_max_percent: float | None = None
    trafo_max_percent: float | None = None


@dataclass(frozen=True)
class ParticipantInjection:
    """A participant's power at its bus for one step, from what it physically did
    (never from its trades)."""

    participant_id: str
    bus_id: str
    production_kw: float
    consumption_kw: float
    net_injection_kw: float


@dataclass(frozen=True)
class GridViolation:
    """One limit violation found by a power flow.

    Attributes:
        code: ``V_LOW``, ``V_HIGH``, ``LINE_OVERLOAD``, ``TRAFO_OVERLOAD`` or
            ``NOT_CONVERGED``.
        element_type: Bus, line or transformer.
        element_id: The element; ``None`` for the whole network.
        observed: Value found.
        limit: Limit exceeded.
    """

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
    line_loading_percent: Mapping[str, float] = field(default_factory=dict)


class GridModel(Protocol):
    """Step-time grid: one power flow per market step."""

    def reset(self, episode_seed: int | None = None, day: str | None = None) -> None:
        """Prepare a fresh working copy of the network for an episode on ``day``."""
        ...

    def assess(
        self, step: int, injections: Sequence[ParticipantInjection]
    ) -> GridAssessment:
        """Run the power flow for ``step`` with the participants' injections and report
        it.
        """
        ...

    def electrical_distance(self, bus_a: str, bus_b: str) -> float:
        """Distance in km along the lines between two buses."""
        ...

    def summary(self) -> NetworkSummary:
        """Totals of the network."""
        ...

    def topology_view(self) -> TopologyView:
        """The network's shape for plots."""
        ...
