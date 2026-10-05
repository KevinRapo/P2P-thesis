"""SimBench's profile classes and how a profile name is classified.

Shared by ``ProfileService`` (the catalogue and its overview) and
``ParticipantService`` (placement filters by load type).
"""

from __future__ import annotations

import re

from src_thesis.application.models import ProfileClass

# SimBench's profile classes, grouped as in its overview of the time series
# (Meinecke et al., 2020, "SimBench—A Benchmark Dataset of Electric Power
# Systems", Energies 13(12), Figures 1 and 8), each with the name pattern that
# recognises its profiles. Order = display order.
CLASSES = (
    (
        ProfileClass(
            key="household",
            group="Load",
            subgroup="Accumulated",
            label="H",
            name="Households",
            description="Standard load profiles of households (H0). The letter "
            "after the dash is a consumption level, e.g. -A low, -H high.",
        ),
        r"H0-",
    ),
    (
        ProfileClass(
            key="commercial",
            group="Load",
            subgroup="Accumulated",
            label="G",
            name="Commercial",
            description="Standard load profiles of businesses (G for Gewerbe): G0 "
            "general, G1 weekdays 8–18 h, G2 evening, G3 continuous, G4 shops, G5 "
            "bakeries, G6 weekends. Suffix: consumption level (-A low, -M medium, "
            "-H high).",
        ),
        r"G\d-",
    ),
    (
        ProfileClass(
            key="agricultural",
            group="Load",
            subgroup="Accumulated",
            label="L",
            name="Agricultural",
            description="Standard load profiles of farms (L for Landwirtschaft): "
            "L0 general, L1 with dairy farming, L2 other farms.",
        ),
        r"L\d-",
    ),
    (
        ProfileClass(
            key="special_slp",
            group="Load",
            subgroup="Accumulated",
            label="BL/WB",
            name="Other standard profiles",
            description="Further standard load profiles with high consumption "
            "(BL-H, WB-H), listed as 'other' in SimBench's overview.",
        ),
        r"(BL|WB)-",
    ),
    (
        ProfileClass(
            key="heat_pump",
            group="Load",
            subgroup="Individual",
            label="HP",
            name="Heat pumps",
            description="One heat pump each: Air_ air-source, Soil_ ground-source. "
            "Parallel, Semi-Parallel and Alternative are the ways the backup "
            "heater runs alongside the pump.",
        ),
        r"(Air|Soil)_",
    ),
    (
        ProfileClass(
            key="ev",
            group="Load",
            subgroup="Individual",
            label="EV",
            name="Electric vehicles",
            description="Charging of one electric vehicle: HLS at home, APLS at "
            "work. The number is mostly the charging power in kW (3.7, 11, 22, "
            "50).",
        ),
        r"(HLS|APLS)_",
    ),
    (
        ProfileClass(
            key="pv",
            group="Generation",
            label="PV",
            name="Photovoltaics",
            description="PV1 … PV8: solar feed-in for two sites (Hanover, Lübeck) "
            "and east, south and west orientation.",
        ),
        r"PV\d",
    ),
    (
        ProfileClass(
            key="wind",
            group="Generation",
            label="Wind",
            name="Wind",
            description="WP1 … WP12 (WP for Windpark): onshore and offshore wind "
            "farms in different regions (North Sea, Baltic Sea, inland).",
        ),
        r"WP\d",
    ),
    (
        ProfileClass(
            key="biomass",
            group="Generation",
            label="BM",
            name="Biomass",
            description="BM1 … BM5: biomass plants, which run almost constantly.",
        ),
        r"BM\d",
    ),
    (
        ProfileClass(
            key="hydro",
            group="Generation",
            label="Hydro",
            name="Hydro power",
            description="Hydro1 … Hydro3: run-of-river hydro power plants.",
        ),
        r"Hydro\d",
    ),
    (
        ProfileClass(
            key="power_plant",
            group="Generation",
            label="Conventional",
            name="Conventional power plants",
            description="pp_1 … : one profile per conventional power plant of the "
            "extra-high-voltage networks; many are constant.",
        ),
        r"pp_",
    ),
    (
        ProfileClass(
            key="storage",
            group="Storage",
            label="Storage",
            name="Storage",
            description="Storage profiles (PV batteries, e-mobility). SimBench "
            "defines the table, but its data set ships none.",
        ),
        None,  # recognised by its table, not its name
    ),
    (
        ProfileClass(
            key="hv_grid",
            group="Aggregated grids",
            label="Omitted HV grids",
            name="Omitted high-voltage grids",
            description="HS0 … HS27, HSexp0/1 (HS for Hochspannung): the total of "
            "a high-voltage grid that SimBench does not model, used by the loads "
            "of the extra-high-voltage networks.",
        ),
        r"HS(exp)?\d",
    ),
    (
        ProfileClass(
            key="grid",
            group="Aggregated grids",
            label="SimBench grids",
            name="SimBench grids",
            description="lv_…, mv_…, hv_…: the total load or generation of a whole "
            "SimBench grid, where the network one level up connects it as one "
            "element (an MV network's LV grids, an HV network's MV grids).",
        ),
        r"(lv|mv|hv)_",
    ),
    (
        ProfileClass(
            key="exchange",
            group="Aggregated grids",
            label="Import",
            name="Import",
            description="imp0, imp1: generators at the edge of the "
            "extra-high-voltage networks that stand for power from neighbouring "
            "grids.",
        ),
        r"imp\d",
    ),
)
BY_KEY = {c.key: c for c, _ in CLASSES}


def category(name: str, table: str) -> str:
    """Class of a SimBench profile from its table and name (``"other"`` if none)."""
    if table == "storage":
        return "storage"
    for profile_class, pattern in CLASSES:
        if pattern and re.match(pattern, name):
            return profile_class.key
    return "other"


def load_class(profile: str) -> str:
    """Class of a load profile, e.g. ``household`` for H0-A."""
    return category(profile, "load")


def description(category: str) -> str:
    """Readable name of a class, empty for ``"other"``."""
    return BY_KEY[category].name if category in BY_KEY else ""
