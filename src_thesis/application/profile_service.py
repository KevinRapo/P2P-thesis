"""ProfileService: profiles and participant mapping (04 §5).

Everything here reads real data: the network's SimBench profiles and SimBench's
complete catalogue (Inspect page), participant placement rules and profile
previews (Participants page), the day split of the time window and the DSO
tariff CSVs (Market & DSO page).
"""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

import src_thesis.marketplace.grid.contract_new as contract
from src_thesis.adapters.grid import participants as mapping
from src_thesis.adapters.grid import simbench_new as adapter
from src_thesis.application.models import (
    ExperimentFile,
    NetworkSource,
    ProfileClass,
    ProfileType,
    Series,
)
from src_thesis.experiments.models.manifest import REPO, data_path
from src_thesis.experiments.models.resolve import resolve_days

# time.resolution -> (adapter resolution, hours per value)
RESOLUTIONS = {"hourly_aggregated": ("hourly", 1.0), "native_15min": ("15min", 0.25)}
PREVIEW_DAYS = 7
TARIFF_FOLDER = "data/prices"
# The CSVs the original MARLEM notebooks use when the file names none.
TARIFF_DEFAULTS = {
    "feed_in": "data/prices/fit_60min.csv",
    "utility": "data/prices/utility_60min.csv",
}

# The eight agents of [P2] Table 6: role, capacity (kW), battery (kWh). The
# demand and generation profile types are a reconstruction: the paper does not
# publish its mapping (I-51).
PAPER_ROLES = (
    ("small_industry", 180, 108.0, "G1-A", "PV3"),
    ("community_hospital", 170, 85.0, "G3-A", "PV2"),
    ("university_campus", 140, 98.0, "G2-A", "PV4"),
    ("shopping_mall", 130, 78.0, "G4-A", "PV1"),
    ("residential_complex", 80, 64.0, "H0-B", "PV5"),
    ("apartment_building", 75, 52.5, "H0-A", "PV6"),
    ("community_solar_farm", 180, 180.0, "H0-C", "PV8"),
    ("parking_lot", 160, 144.0, "G6-A", "PV7"),
)
# Mapping CSV columns (import_mapping); lists are separated by ";".
MAPPING_COLUMNS = (
    "id",
    "role",
    "bus",
    "loads",
    "sgens",
    "profile_source",
    "demand",
    "generation",
    "scaling_mode",
    "demand_target",
    "generation_target",
    "battery_kwh",
)


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

    Every method reads real data; none returns sample data any more.
    """

    SAMPLE_DATA = False

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

    def placement_rules(self) -> dict[str, str]:
        """The placement rules ``suggest_mapping`` knows, with what they select."""
        return dict(mapping.RULES)

    def suggest_mapping(self, source: NetworkSource, rule: dict) -> list[dict]:
        """Participants placed on a network by a seeded rule (01 §3.1).

        Built: each agent owns one load and the free generators at its bus, with
        their own SimBench profiles (``native``) and no scaling.

        Args:
            source: The network to place participants on.
            rule: ``{"type": <rule>, "n": <agents>, "seed": <int>}``; the types
                are listed by ``placement_rules``.

        Returns:
            Participant entries for the experiment file's ``participants`` list.

        Raises:
            ValueError: Unknown rule, or not enough candidates in the network.
        """
        ref = contract.NetworkRef(source.type, source.code)
        return mapping.place(adapter.elements(ref), adapter.topology_view(ref), rule)

    def paper_roles(self, participants: list[dict]) -> list[dict]:
        """The first eight participants turned into the agents of [P2] Table 6.

        Built: keeps each agent's bus and owned elements; sets its role, catalogue
        profiles (a reconstruction, I-51), its capacity as peak kW and its battery
        (95 % efficiency, SoC 5–95 %).

        Raises:
            ValueError: There are no participants to change.
        """
        if not participants:
            raise ValueError("Add or place participants first; the roles change them")
        out = [dict(p) for p in participants]
        for p, (role, kw, battery, demand, generation) in zip(out, PAPER_ROLES):
            p.update(
                id=role,
                role=role,
                profile={
                    "source": "catalog",
                    "demand": {"type": demand},
                    "generation": {"type": generation},
                },
                scaling={"mode": "peak_kw", "demand": kw, "generation": kw},
                battery={
                    "nominal_capacity_kwh": battery,
                    "min_soc": 0.05,
                    "max_soc": 0.95,
                    "charge_efficiency": 0.95,
                    "discharge_efficiency": 0.95,
                },
            )
        return out

    def import_mapping(self, content: bytes, filename: str) -> list[dict]:
        """Participants read from a mapping file (01 §3.1, mode ``file``).

        Built: a JSON file holds a participant list (or ``{"participants": [...]}``)
        in the experiment file's format; a CSV file has the columns
        ``MAPPING_COLUMNS``, with lists separated by ``;``.

        Raises:
            ValueError: Unreadable file, or an entry without ``id`` or ``bus``.
        """
        text = content.decode("utf-8-sig")
        if filename.lower().endswith(".json"):
            data = json.loads(text)
            rows = data.get("participants", []) if isinstance(data, dict) else data
            if not isinstance(rows, list):
                raise ValueError("The JSON file holds no participant list")
        elif filename.lower().endswith(".csv"):
            rows = [_participant_from_csv(r) for r in csv.DictReader(io.StringIO(text))]
        else:
            raise ValueError("Use a .json or .csv mapping file")
        for i, row in enumerate(rows, start=1):
            if not isinstance(row, dict) or not row.get("id") or not row.get("bus"):
                raise ValueError(f"Entry {i} has no id or no bus")
        return rows

    def preview(
        self, file: ExperimentFile, participant_id: str, days: int = PREVIEW_DAYS
    ) -> Series:
        """Demand, generation and net power of one participant, in kW.

        Built: the participant's profiles (its owned elements' own for
        ``native``, a SimBench catalogue profile for ``catalog``) scaled as the
        file says (01 §3.4), at the file's resolution, for ``days`` days from the
        start of the time window.

        Raises:
            ValueError: Unknown participant, a profile source without preview
                (``csv``, ``synthetic``) or a scaling that cannot be applied.
        """
        p = next((x for x in file.participants if x.get("id") == participant_id), None)
        if p is None:
            raise ValueError(f"No participant {participant_id!r}")
        resolution, step_hours = RESOLUTIONS[
            file.time.get("resolution", "hourly_aggregated")
        ]
        start = _window_start(file)
        source = NetworkSource(**file.grid.get("source", {}))
        ref = contract.NetworkRef(source.type, source.code)
        scaling = p.get("scaling") or {}
        x: list[str] = []
        y: dict[str, list[float]] = {}
        for side, owned in (("demand", "loads"), ("generation", "sgens")):
            series = _side(ref, p, side, owned, start, days, resolution)
            if series is None:
                continue
            x, window, year = series
            values = mapping.scale(
                window,
                year,
                scaling.get("mode", "none"),
                scaling.get(side),
                step_hours,
            )
            y[side] = [round(v, 2) for v in values]
        if y:
            demand = y.get("demand", [0.0] * len(x))
            generation = y.get("generation", [0.0] * len(x))
            y["net (generation − demand)"] = [
                round(g - d, 2) for g, d in zip(generation, demand)
            ]
        return Series(x=x, y=y, x_label="time", y_label="kW")

    def days(self, file: ExperimentFile) -> dict[str, list[str]]:
        """The training and evaluation dates the file's ``time`` section selects.

        Built: ``experiments.models.resolve.resolve_days`` on ``file.time``.

        Raises:
            ValueError: The time section selects no dates or is incomplete.
        """
        try:
            split = resolve_days(file.time)
        except KeyError as missing:
            raise ValueError(f"time.days needs {missing}") from None
        return {"train": list(split.train), "eval": list(split.eval)}

    def data_files(self, folder: str) -> dict[str, list[str]]:
        """The CSVs in a data folder of the repository, with their columns.

        Built: e.g. ``data/demand``, ``data/generation`` or ``data/prices``; each
        column is one profile. Paths are repository-relative, as the file stores
        them.

        Raises:
            ValueError: ``folder`` is not inside the repository's ``data``.
        """
        root = (REPO / "data").resolve()
        path = (REPO / folder).resolve()
        if path != root and root not in path.parents:
            raise ValueError(f"{folder!r} is not a data folder")
        return {
            f"{folder.rstrip('/')}/{csv_path.name}": _csv_columns(csv_path)
            for csv_path in sorted(path.glob("*.csv"))
        }

    def tariff_files(self) -> dict[str, list[str]]:
        """The DSO tariff CSVs (``data/prices``); each column is one daily profile."""
        return self.data_files(TARIFF_FOLDER)

    def tariffs(self, file: ExperimentFile) -> Series:
        """The DSO tariff profiles the file selects, as stored in the CSVs.

        Built: for ``dso.tariffs.source = "csv"``, the feed-in and utility CSVs
        (or the original defaults) over one day; one line per column, or only the
        chosen column. These are the raw values: the DSO maps them into the
        market's price bounds when the environment runs. ``synthetic`` tariffs are
        generated per episode, so there is no fixed curve (empty series).
        """
        tariffs = file.dso.get("tariffs", {})
        if tariffs.get("source", "synthetic") != "csv":
            return Series(x=[], y={}, x_label="time of day", y_label="price")
        x: list[str] = []
        y: dict[str, list[float]] = {}
        for key, label in (("feed_in", "feed-in"), ("utility", "utility")):
            spec = tariffs.get(key) or {"path": TARIFF_DEFAULTS[key]}
            columns = _read_csv(data_path(spec["path"]))
            chosen = [spec["column"]] if spec.get("column") else list(columns)
            for column in chosen:
                if column not in columns:
                    raise ValueError(f"{spec['path']} has no column {column!r}")
                values = columns[column]
                y[f"{label} · {column}"] = values
                x = x if len(x) >= len(values) else _times_of_day(len(values))
        return Series(x=x, y=y, x_label="time of day", y_label="price")


def _window_start(file: ExperimentFile) -> str:
    """First day of the time window: the fixed date, or the start of the range."""
    days = file.time.get("days") or {}
    start = days.get("date") if days.get("mode", "fixed") == "fixed" else None
    return str(start or days.get("start") or f"{adapter.SIMBENCH_YEAR}-01-01")


def _side(
    ref: contract.NetworkRef,
    participant: dict[str, Any],
    side: str,
    owned: str,
    start: str,
    days: int,
    resolution: str,
) -> tuple[list[str], list[float], list[float]] | None:
    """(labels, window values, year values) of a participant's demand or
    generation before scaling; ``None`` if it has none.
    """
    profile = participant.get("profile") or {}
    source = profile.get("source", "native")
    year_start = f"{adapter.SIMBENCH_YEAR}-01-01"
    if source == "native":
        ids = (participant.get("owns") or {}).get(owned) or []
        if not ids:
            return None
        x, window = adapter.element_power(ref, ids, start, days, resolution)
        _, year = adapter.element_power(ref, ids, year_start, 366, resolution)
        return x, _total(window), _total(year)
    if source == "catalog":
        name = (profile.get(side) or {}).get("type")
        if not name:
            return None
        x, window = adapter.catalogue_series([name], start, days, resolution)
        _, year = adapter.catalogue_series([name], year_start, 366, resolution)
        if name not in window:
            raise ValueError(f"SimBench has no profile {name!r}")
        mode = (participant.get("scaling") or {}).get("mode", "none")
        if mode == "none":  # no target: take the owned elements' rated power
            rated = _rated_kw(ref, (participant.get("owns") or {}).get(owned) or [])
            if not rated:
                raise ValueError(
                    f"The {side} profile {name} is a factor of rated power: set a "
                    "scaling (peak kW or annual energy) or own an element"
                )
            return x, [v * rated for v in window[name]], [v * rated for v in year[name]]
        return x, window[name], year[name]
    raise ValueError(f"No preview for profile source {source!r} yet")


def _total(values: dict[str, list[float]]) -> list[float]:
    """Element-wise sum of several series."""
    return [sum(v) for v in zip(*values.values())] if values else []


def _rated_kw(ref: contract.NetworkRef, ids: list[str]) -> float:
    """Sum of the rated power of the named elements, in kW."""
    wanted = set(ids)
    return sum(e.rated_kw for e in adapter.elements(ref) if e.id in wanted)


def _participant_from_csv(row: dict[str, str]) -> dict[str, Any]:
    """One participant entry from a mapping CSV row (``MAPPING_COLUMNS``)."""

    def split(value: str | None) -> list[str]:
        return [v.strip() for v in (value or "").split(";") if v.strip()]

    def number(value: str | None) -> float | None:
        return float(value) if value not in (None, "") else None

    source = (row.get("profile_source") or "native").strip()
    profile: dict[str, Any] = {"source": source}
    for side in ("demand", "generation"):
        if row.get(side):
            profile[side] = {"type": row[side].strip()}
    scaling: dict[str, Any] = {"mode": (row.get("scaling_mode") or "none").strip()}
    for side in ("demand", "generation"):
        target = number(row.get(f"{side}_target"))
        if target is not None:
            scaling[side] = target
    battery_kwh = number(row.get("battery_kwh"))
    return {
        "id": (row.get("id") or "").strip(),
        "role": (row.get("role") or "").strip(),
        "bus": (row.get("bus") or "").strip(),
        "owns": {"loads": split(row.get("loads")), "sgens": split(row.get("sgens"))},
        "profile": profile,
        "scaling": scaling,
        "battery": {"nominal_capacity_kwh": battery_kwh} if battery_kwh else None,
    }


def _read_csv(path: Any) -> dict[str, list[float]]:
    """Column -> values of a numeric CSV; empty cells (shorter columns) are left
    out.
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return {}
    return {c: [float(r[c]) for r in rows if (r[c] or "").strip()] for c in rows[0]}


def _csv_columns(path: Any) -> list[str]:
    """The header of a CSV."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return next(csv.reader(f), [])


def _times_of_day(rows: int) -> list[str]:
    """``HH:MM`` labels for ``rows`` equal steps over one day."""
    minutes = 24 * 60 // max(rows, 1)
    return [f"{i * minutes // 60:02d}:{i * minutes % 60:02d}" for i in range(rows)]
