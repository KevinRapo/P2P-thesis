"""Plain data returned by application services.

These models are the only types that cross the boundary between the services
and their callers (the Studio, notebooks). They stay free of market objects and
pandapower nets.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------------------
# Networks: catalog, facts, topology, power flow
# --------------------------------------------------------------------------------------
class NetworkSource(BaseModel):
    """Which network.

    Attributes:
        type: ``"simbench"``, ``"pandapower_builtin"`` or ``"pandapower_file"``.
        code: SimBench code, pandapower function name or file path.
    """

    type: Literal["simbench", "pandapower_builtin", "pandapower_file"]
    code: str


class NetworkInfo(BaseModel):
    """Catalog entry. Counts and flags are ``None`` until the network is loaded.

    Attributes:
        category: SimBench network type (rural, semi-urban, urban, commercial,
            mixed); ``None`` for other sources.
        scenario: SimBench scenario: 0 today, 1 and 2 future (more PV, storage,
            heat pumps and electric vehicles).
        switches: Whether the SimBench network models its switches.
    """

    source: NetworkSource
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


ProfileCategory = Literal[
    "household",
    "commercial",
    "agricultural",
    "special_slp",
    "heat_pump",
    "ev",
    "pv",
    "wind",
    "biomass",
    "hydro",
    "power_plant",
    "storage",
    "hv_grid",
    "grid",
    "exchange",
    "other",
]


# --------------------------------------------------------------------------------------
# Profiles: classes, types, series
# --------------------------------------------------------------------------------------
class ProfileClass(BaseModel):
    """One class of SimBench profiles, grouped as in SimBench's own overview of its
    time series (Meinecke et al., 2020, Figure 1).

    Attributes:
        key: The category, as in ``ProfileType.category``.
        group: ``"Load"``, ``"Generation"``, ``"Storage"`` or ``"Aggregated grids"``.
        subgroup: ``"Accumulated"`` or ``"Individual"`` for loads, else ``""``.
        label: Short label as in SimBench's figure, e.g. ``"H"`` or ``"PV"``.
        name: Readable name, e.g. ``"Households"``.
        description: What the profiles describe and how they are named.
    """

    key: ProfileCategory
    group: str
    subgroup: str = ""
    label: str
    name: str
    description: str


class ProfileType(BaseModel):
    """A profile that can be assigned to a participant (SimBench catalogue).

    Attributes:
        code: Profile name, e.g. ``"H0-B"`` (household) or ``"PV3"``.
        category: Its class (see ``ProfileClass``).
        description: Readable explanation.
        table: SimBench profile table it comes from (``load``, ``renewables``, …).
        quantities: ``["p"]``, or ``["p", "q"]`` for loads.
        elements: Number of network elements that use it.
        mean: Mean active-power factor over the year (1.0 = rated power).
        peak: Highest active-power factor over the year.
    """

    code: str
    category: ProfileCategory
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
