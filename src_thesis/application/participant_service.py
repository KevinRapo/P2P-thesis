"""ParticipantService: placing participants on a network and previewing them
(04 §5, 01 §3).

Placement by combined filters, mapping import, the [P2] Table 6 roles, and each
participant's demand and generation as the file scales them.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

import src_thesis.core.grid_contract as contract
from src_thesis.adapters.grid import participants as mapping
from src_thesis.adapters.grid import simbench_new as adapter
from src_thesis.application.models import ExperimentFile, NetworkSource, Series
from src_thesis.application.profile_classes import BY_KEY, CLASSES, load_class

# time.resolution -> (adapter resolution, hours per value)
RESOLUTIONS = {"hourly_aggregated": ("hourly", 1.0), "native_15min": ("15min", 0.25)}
PREVIEW_DAYS = 7
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


class ParticipantService:
    """Participants of an experiment: where they sit, what they own, how they
    behave (Participants page)."""

    SAMPLE_DATA = False

    def placement_options(self, source: NetworkSource) -> dict[str, Any]:
        """What the placement filters can choose from on a network (01 §3.1).

        Built: the load classes present, each with the number of buses that have
        such a load, and the choices of the other filters.

        Returns:
            ``{"loads": {class: "Name (n buses)"}, "generation": {…},
            "storage": {…}, "position": {…}, "owns": {…}, "default": {…}}``.
        """
        ref = contract.NetworkRef(source.type, source.code)
        buses: dict[str, set[str]] = {}
        for e in adapter.elements(ref):
            if e.element_type == "load":
                buses.setdefault(load_class(e.profile_type), set()).add(e.bus)
        order = [c.key for c, _ in CLASSES] + ["other"]
        loads = {
            key: f"{BY_KEY[key].name if key in BY_KEY else 'Other'} "
            f"({len(buses[key])} buses)"
            for key in sorted(buses, key=order.index)
        }
        return {
            "loads": loads,
            "generation": dict(mapping.GENERATION),
            "storage": dict(mapping.STORAGE),
            "position": dict(mapping.POSITIONS),
            "owns": dict(mapping.OWNS),
            "default": dict(mapping.DEFAULT_RULE),
        }

    def placement_candidates(self, source: NetworkSource, rule: dict) -> list[str]:
        """The buses that pass a placement rule's filters, in network order.

        Built: what ``suggest_mapping`` draws its agents from.

        Raises:
            ValueError: An unknown filter value.
        """
        ref = contract.NetworkRef(source.type, source.code)
        return mapping.candidates(
            adapter.elements(ref), adapter.topology_view(ref), rule, load_class
        )

    def suggest_mapping(self, source: NetworkSource, rule: dict) -> list[dict]:
        """Participants placed on a network by a seeded rule (01 §3.1).

        Built: ``n`` of the buses that pass the rule's filters (load classes,
        generation, storage, position) become agents. Each owns its bus (or only
        the matching loads), with the elements' own SimBench profiles
        (``native``) and no scaling or battery.

        Args:
            source: The network to place participants on.
            rule: The filters, ``n`` and ``seed``; see ``placement_options``.

        Returns:
            Participant entries for the experiment file's ``participants`` list.

        Raises:
            ValueError: An unknown filter value, or fewer candidates than ``n``.
        """
        ref = contract.NetworkRef(source.type, source.code)
        return mapping.place(
            adapter.elements(ref), adapter.topology_view(ref), rule, load_class
        )

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
