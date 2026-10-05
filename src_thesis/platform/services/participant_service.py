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

import src_thesis.marlem.grid.contract as contract
from src_thesis.marlem.grid import placement as mapping
from src_thesis.marlem.grid import simbench as adapter
from src_thesis.platform.services.models import ExperimentFile, NetworkSource, Series
from src_thesis.platform.kernel.models.sections import Participant
from src_thesis.platform.kernel.factory.profiles import (
    RESOLUTIONS,
    participant_power,
    window_start,
)

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

    def placement_candidates(self, source: NetworkSource) -> list[str]:
        """The buses that can be participants: those with a generator or storage.

        Built: what ``suggest_mapping`` turns into participants; every other bus
        with load stays background.
        """
        ref = contract.NetworkRef(source.type, source.code)
        return mapping.candidates(adapter.elements(ref))

    def suggest_mapping(self, source: NetworkSource) -> list[dict]:
        """One participant per flexible bus of a network (01 §3.1).

        Built: every bus with a generator or storage becomes a participant that
        owns everything at its bus, with the elements' own SimBench profiles
        (``native``) and no scaling or battery. Buses with only load are not
        participants; they stay background.

        Args:
            source: The network to place participants on.

        Returns:
            Participant entries for the experiment file's ``participants`` list.
        """
        ref = contract.NetworkRef(source.type, source.code)
        return mapping.place(adapter.elements(ref))

    def paper_roles(self, participants: list[Participant]) -> list[dict]:
        """The first eight participants turned into the agents of [P2] Table 6.

        Built: keeps each agent's bus and owned elements; sets its role, catalogue
        profiles (a reconstruction, I-51), its capacity as peak kW and its battery
        (95 % efficiency, SoC 5–95 %).

        Raises:
            ValueError: There are no participants to change.
        """
        if not participants:
            raise ValueError("Add or place participants first; the roles change them")
        out = [p.model_dump(mode="json", exclude_unset=True) for p in participants]
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
        p = next((x for x in file.participants if x.id == participant_id), None)
        if p is None:
            raise ValueError(f"No participant {participant_id!r}")
        resolution, step_hours = RESOLUTIONS[
            file.time.resolution or "hourly_aggregated"
        ]
        start = window_start(file)
        source = file.grid.source
        if source is None or not source.type or not source.code:
            raise ValueError("The draft has no network (grid.source)")
        ref = contract.NetworkRef(source.type, source.code)
        x, power = participant_power(ref, p, start, days, resolution, step_hours)
        y = {k: [round(v, 2) for v in vs] for k, vs in power.items()}
        if y:
            demand = y.get("demand", [0.0] * len(x))
            generation = y.get("generation", [0.0] * len(x))
            y["net (generation − demand)"] = [
                round(g - d, 2) for g, d in zip(generation, demand)
            ]
        return Series(x=x, y=y, x_label="time", y_label="kW")


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
