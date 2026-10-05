"""A participant's demand and generation as the experiment file describes them.

Pure functions over the SimBench adapter: the Studio's profile preview and the
environment factory share them, so what the preview shows is what the market runs.
"""

from __future__ import annotations

import src_thesis.marlem.grid.contract as contract
from src_thesis.marlem.grid import placement as mapping
from src_thesis.marlem.grid import simbench as adapter
from src_thesis.platform.kernel.models.records import ExperimentFile
from src_thesis.platform.kernel.models.sections import (
    Days,
    Owns,
    Participant,
    ParticipantProfile,
    ProfileRef,
    Scaling,
)

# time.resolution -> (adapter resolution, hours per value)
RESOLUTIONS = {"hourly_aggregated": ("hourly", 1.0), "native_15min": ("15min", 0.25)}


def window_start(file: ExperimentFile) -> str:
    """First day of the time window: the fixed date, or the start of the range."""
    days = file.time.days or Days()
    start = days.date if (days.mode or "fixed") == "fixed" else None
    return str(start or days.start or f"{adapter.SIMBENCH_YEAR}-01-01")


def side(
    ref: contract.NetworkRef,
    participant: Participant,
    side: str,
    owned: str,
    start: str,
    days: int,
    resolution: str,
) -> tuple[list[str], list[float], list[float]] | None:
    """(labels, window values, year values) of a participant's demand or
    generation before scaling; ``None`` if it has none.
    """
    profile = participant.profile or ParticipantProfile()
    owns = participant.owns or Owns()
    source = profile.source or "native"
    year_start = f"{adapter.SIMBENCH_YEAR}-01-01"
    if source == "native":
        ids = getattr(owns, owned) or []
        if not ids:
            return None
        x, window = adapter.element_power(ref, ids, start, days, resolution)
        _, year = adapter.element_power(ref, ids, year_start, 366, resolution)
        return x, total(window), total(year)
    if source == "catalog":
        name = (getattr(profile, side) or ProfileRef()).type
        if not name:
            return None
        x, window = adapter.catalogue_series([name], start, days, resolution)
        _, year = adapter.catalogue_series([name], year_start, 366, resolution)
        if name not in window:
            raise ValueError(f"SimBench has no profile {name!r}")
        mode = (participant.scaling or Scaling()).mode or "none"
        if mode == "none":  # no target: take the owned elements' rated power
            rated = rated_kw(ref, getattr(owns, owned) or [])
            if not rated:
                raise ValueError(
                    f"The {side} profile {name} is a factor of rated power: set a "
                    "scaling (peak kW or annual energy) or own an element"
                )
            return x, [v * rated for v in window[name]], [v * rated for v in year[name]]
        return x, window[name], year[name]
    raise ValueError(f"No preview for profile source {source!r} yet")


def total(values: dict[str, list[float]]) -> list[float]:
    """Element-wise sum of several series."""
    return [sum(v) for v in zip(*values.values())] if values else []


def rated_kw(ref: contract.NetworkRef, ids: list[str]) -> float:
    """Sum of the rated power of the named elements, in kW."""
    wanted = set(ids)
    return sum(e.rated_kw for e in adapter.elements(ref) if e.id in wanted)


def participant_power(
    ref: contract.NetworkRef,
    participant: Participant,
    start: str,
    days: int,
    resolution: str,
    step_hours: float,
) -> tuple[list[str], dict[str, list[float]]]:
    """Scaled demand and generation of a participant in kW, keyed ``"demand"`` and
    ``"generation"`` (missing when it has none)."""
    scaling = participant.scaling or Scaling()
    x: list[str] = []
    out: dict[str, list[float]] = {}
    for name, owned in (("demand", "loads"), ("generation", "sgens")):
        series = side(ref, participant, name, owned, start, days, resolution)
        if series is None:
            continue
        x, window, year = series
        out[name] = mapping.scale(
            window, year, scaling.mode or "none", getattr(scaling, name), step_hours
        )
    return x, out
