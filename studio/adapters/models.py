"""Plain data only the Studio needs: profile classes, profile types, chart series.

Everything about networks (catalogue, topology, elements, power flow) comes from the
grid contract (``core/grid/contract.py``) as it is.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

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


class DayElement(BaseModel):
    """One load, generator or storage unit on the scenario's day.

    Attributes:
        id: Element name.
        element_type: ``"load"``, ``"sgen"`` or ``"storage"``.
        bus: Bus it is connected to.
        profile_type: SimBench profile name; empty if none.
        owner: Participant that took it over; empty for the background.
        kw: Active power per market step, in kW (positive for all three types).
    """

    id: str
    element_type: str
    bus: str
    profile_type: str = ""
    owner: str = ""
    kw: list[float]


class DayProfiles(BaseModel):
    """What every element of the network does on the scenario's day.

    Attributes:
        x: Time label of each market step.
        step_hours: Hours per step, to turn kW into kWh.
        elements: Every element; ``owner`` tells participants from background.
    """

    x: list[str]
    step_hours: float
    elements: list[DayElement]

    def owned(self, participant: str | None = None) -> list[DayElement]:
        """Elements taken over by one participant, or by any when ``None``."""
        return [
            e
            for e in self.elements
            if e.owner and (participant is None or e.owner == participant)
        ]

    def background(self) -> list[DayElement]:
        """Elements no participant owns."""
        return [e for e in self.elements if not e.owner]

    def total_kw(self, elements: list[DayElement]) -> list[float]:
        """The elements' summed power per step."""
        return [sum(e.kw[t] for e in elements) for t in range(len(self.x))]

    def kwh(self, elements: list[DayElement]) -> float:
        """The elements' energy over the day."""
        return sum(sum(e.kw) for e in elements) * self.step_hours
