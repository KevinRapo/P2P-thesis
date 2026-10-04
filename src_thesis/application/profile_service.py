"""ProfileService: profiles and participant mapping (04 §5).

``profile_types`` and ``profile_series`` read the network's real SimBench profiles
(the Grid page's profile inspector). The other methods still return generated
sample data; each docstring says what the final version will do (R3, 01 §3).
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
import src_thesis.marketplace.grid.contract_new as contract
from src_thesis.adapters.grid import simbench_new as adapter
from src_thesis.application.models import (
    ExperimentFile,
    NetworkSource,
    ProfileClass,
    ProfileType,
    Series,
)


def _participants(n: int = 8) -> list[dict]:
    roles = [
        ("small_industry", "G1-A", "PV3", 180),
        ("community_hospital", "G3-A", "PV2", 170),
        ("university_campus", "G2-A", "PV4", 140),
        ("shopping_mall", "G4-A", "PV1", 130),
        ("residential_complex", "H0-B", "PV5", 80),
        ("apartment_building", "H0-A", "PV6", 75),
        ("community_solar_farm", "H0-C", "PV8", 180),
        ("parking_lot", "G6-A", "PV7", 160),
    ]
    out = []
    for i, (role, demand, gen, peak) in enumerate(roles[:n]):
        out.append(
            {
                "id": role,
                "role": role,
                "bus": f"LV4.101 Bus {10 + 3 * i}",
                "owns": {"loads": [f"LV4.101 Load {5 + 2 * i}"], "sgens": []},
                "profile": {
                    "source": "catalog",
                    "demand": {"type": demand},
                    "generation": {"type": gen},
                },
                "scaling": {"mode": "peak_kw", "demand": peak, "generation": peak},
                "battery": (
                    {
                        "nominal_capacity_kwh": round(peak * 0.6, 1),
                        "min_soc": 0.1,
                        "max_soc": 0.9,
                        "charge_efficiency": 0.95,
                        "discharge_efficiency": 0.95,
                    }
                    if i % 3 != 2
                    else None
                ),
            }
        )
    return out


HOURS = list(range(24))


# SimBench's profile classes, grouped as in its overview of the time series
# (Meinecke et al., 2020, "SimBench—A Benchmark Dataset of Electric Power
# Systems", Energies 13(12), Figures 1 and 8), each with the name pattern that
# recognises its profiles. Order = display order.
_CLASSES = (
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
_BY_KEY = {c.key: c for c, _ in _CLASSES}


def _category(name: str, table: str) -> str:
    """Class of a SimBench profile from its table and name (``"other"`` if none)."""
    if table == "storage":
        return "storage"
    for profile_class, pattern in _CLASSES:
        if pattern and re.match(pattern, name):
            return profile_class.key
    return "other"


def _description(category: str) -> str:
    """Readable name of a class, empty for ``"other"``."""
    return _BY_KEY[category].name if category in _BY_KEY else ""


class ProfileService:
    """Generation and demand profiles and how participants map onto a network (R3).

    Every method returns sample data until it is built; its docstring says what the
    final version will do.
    """

    SAMPLE_DATA = True  # shown in the Studio's header until the service is built

    def profile_classes(self) -> list[ProfileClass]:
        """SimBench's profile classes, grouped as in SimBench's own overview.

        Built: a fixed list (load: accumulated and individual; generation;
        storage; aggregated grids). Every ``ProfileType.category`` is one of
        their keys, or ``"other"``.
        """
        return [profile_class for profile_class, _ in _CLASSES]

    def profile_types(self, source: NetworkSource) -> list[ProfileType]:
        """The SimBench profiles a network ships, with how many elements use each.

        Built: read from the network through the pandapower adapter. Networks
        without profiles (pandapower built-ins) return an empty list.
        """
        ref = contract.NetworkRef(source.type, source.code)
        return [
            ProfileType(
                code=r.name,
                category=_category(r.name, r.table),
                description=_description(_category(r.name, r.table)),
                table=r.table,
                quantities=list(r.quantities),
                elements=r.elements,
                mean=r.mean,
                peak=r.peak,
            )
            for r in adapter.profile_catalog(ref)
        ]

    def profile_series(
        self,
        source: NetworkSource,
        codes: list[str],
        start: str,
        days: int = 7,
        resolution: str = "hourly",
        quantity: str = "p",
    ) -> Series:
        """Values of SimBench profiles over a time window, for inspection.

        Built: read from the network through the pandapower adapter.

        Args:
            source: The network whose profiles are read.
            codes: Profile names, as returned by ``profile_types``.
            start: First day (``YYYY-MM-DD``, in the profile year 2016).
            days: Length of the window in days.
            resolution: ``"15min"`` (raw), ``"hourly"`` or ``"daily"`` (means).
            quantity: ``"p"`` (active) or ``"q"`` (reactive; loads only).

        Returns:
            One y series per profile, as factors of the element's rated power.
        """
        ref = contract.NetworkRef(source.type, source.code)
        x, y = adapter.profile_series(ref, codes, start, days, resolution, quantity)
        return Series(
            x=x,
            y=y,
            x_label="time",
            y_label=f"{quantity} (factor of rated power)",
        )

    def profile_power(
        self,
        source: NetworkSource,
        codes: list[str],
        start: str,
        days: int = 7,
        resolution: str = "hourly",
        quantity: str = "p",
        per_element: bool = False,
    ) -> Series:
        """SimBench profiles scaled by the rated power of the elements using them.

        Built: each element's power is its profile factor times its rated power
        (SimBench's absolute values), summed per profile or shown per element.

        Args:
            source: The network.
            codes: Profile names, as returned by ``profile_types``.
            start: First day (``YYYY-MM-DD``, in the profile year 2016).
            days: Length of the window in days.
            resolution: ``"15min"`` (raw), ``"hourly"`` or ``"daily"`` (means).
            quantity: ``"p"`` (kW) or ``"q"`` (kvar; loads only).
            per_element: One series per element instead of one sum per profile.

        Returns:
            One y series per profile (e.g. "H0-A (6)": its six elements summed) or
            per element, in kW or kvar.
        """
        ref = contract.NetworkRef(source.type, source.code)
        x, y = adapter.profile_power(
            ref, codes, start, days, resolution, quantity, per_element
        )
        unit = "kW" if quantity == "p" else "kvar"
        return Series(x=x, y=y, x_label="time", y_label=f"{quantity} ({unit})")

    def catalogue_types(self, scenario: int = 0) -> list[ProfileType]:
        """Every profile SimBench ships, independent of any network.

        Built: read from SimBench's complete data set. ``elements`` is 0, as no
        network is involved.

        Args:
            scenario: SimBench scenario (0 = today, 1 and 2 = future scenarios).
        """
        return [
            ProfileType(
                code=r.name,
                category=_category(r.name, r.table),
                description=_description(_category(r.name, r.table)),
                table=r.table,
                quantities=list(r.quantities),
                elements=0,
                mean=r.mean,
                peak=r.peak,
            )
            for r in adapter.catalogue_profiles(scenario)
        ]

    def catalogue_series(
        self,
        codes: list[str],
        start: str,
        days: int = 7,
        resolution: str = "hourly",
        quantity: str = "p",
        scenario: int = 0,
    ) -> Series:
        """Values of catalogue profiles over a time window, as factors of rated
        power.

        Built: read from SimBench's complete data set. Arguments as in
        ``profile_series``, without a network.
        """
        x, y = adapter.catalogue_series(
            codes, start, days, resolution, quantity, scenario
        )
        return Series(
            x=x,
            y=y,
            x_label="time",
            y_label=f"{quantity} (factor of rated power)",
        )

    def preview(self, file: ExperimentFile, participant_id: str) -> Series:
        """Generation, demand and net profile of one participant over time.

        Sample data for now. The final version will load the participant's profiles,
        apply scaling and resolution (01 §3.4).
        """
        p = next(
            (x for x in file.participants if x["id"] == participant_id),
            file.participants[0] if file.participants else {},
        )
        peak = float(p.get("scaling", {}).get("generation", 100))
        gen = [
            round(max(0.0, peak * math.exp(-(((h - 12.5) / 3.2) ** 2))), 1)
            for h in HOURS
        ]
        dem = [
            round(
                peak
                * (
                    0.35
                    + 0.25 * math.exp(-(((h - 8) / 2) ** 2))
                    + 0.35 * math.exp(-(((h - 19) / 2.5) ** 2))
                ),
                1,
            )
            for h in HOURS
        ]
        return Series(
            x=HOURS,
            y={
                "generation": gen,
                "demand": dem,
                "net": [round(g - d, 1) for g, d in zip(gen, dem)],
            },
            x_label="hour",
            y_label="kW",
        )

    def suggest_mapping(self, source: NetworkSource, rule: dict) -> list[dict]:
        """Participants placed on a network by a rule, e.g. "8 households with PV".

        Sample data for now. The final version will place participants on the network by
        a seeded rule (01 §3.1).

        Args:
            source: The network to place participants on.
            rule: The placement rule, e.g. ``{"type": "household_with_pv", "n": 8}``.

        Returns:
            Participant entries for the experiment file's ``participants`` list.
        """
        return _participants(int(rule.get("n", 8)))

    def days(self, file: ExperimentFile) -> dict[str, list[str]]:
        """The training and evaluation dates the file's ``time`` section selects.

        Sample data for now. The final version will call
        ``experiments.models.resolve.resolve_days`` on ``file.time``.
        """
        start = datetime(2016, 5, 2)
        days = [
            (start + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(0, 120)
            if (start + timedelta(days=i)).weekday() < 5
        ]
        cut = int(len(days) * 0.8)
        return {"train": days[:cut], "eval": days[cut:]}

    def tariffs(self, file: ExperimentFile) -> Series:
        """Feed-in tariff and utility price over the time window.

        Sample data for now. The final version will read the DSO tariff CSVs or the
        synthetic generator over the window.
        """
        fit = [
            round(40 + 25 * math.sin(math.pi * (h - 6) / 12) if 6 <= h <= 18 else 35, 1)
            for h in HOURS
        ]
        util = [
            round(v * 2.4 + (60 if 17 <= h <= 21 else 0), 1) for h, v in zip(HOURS, fit)
        ]
        return Series(
            x=HOURS,
            y={"feed-in tariff": fit, "utility price": util},
            x_label="hour",
            y_label="price",
        )
