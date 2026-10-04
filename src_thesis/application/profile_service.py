"""ProfileService: profiles and participant mapping (04 §5).

Final implementation: ``SimBenchProfileService``, not built yet (R3). Demo:
``DemoProfileService`` (generated sample curves).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Protocol
from src_thesis.application.config_service import _participants
from src_thesis.application.models import (
    ExperimentFile,
    NetworkSource,
    ProfileType,
    Series,
)


# ---------------------------------------------------------------------- protocol
class ProfileService(Protocol):
    """Generation and demand profiles and how participants map onto a network (R3)."""

    def profile_types(self, source: NetworkSource | None = None) -> list[ProfileType]:
        """Profile types that can be assigned (SimBench catalogue)."""
        ...

    def preview(self, file: ExperimentFile, participant_id: str) -> Series:
        """Generation, demand and net profile of one participant over time."""
        ...

    def suggest_mapping(self, source: NetworkSource, rule: dict) -> list[dict]:
        """Participants placed on a network by a rule, e.g. "8 households with PV".

        Args:
            source: The network to place participants on.
            rule: The placement rule, e.g. ``{"type": "household_with_pv", "n": 8}``.

        Returns:
            Participant entries for the experiment file's ``participants`` list.
        """
        ...

    def days(self, file: ExperimentFile) -> dict[str, list[str]]:
        """The training and evaluation dates the file's ``time`` section selects."""
        ...

    def tariffs(self, file: ExperimentFile) -> Series:
        """Feed-in tariff and utility price over the time window."""
        ...


# ---------------------------------------------------------------------- final implementation (skeleton)
_NOT_BUILT = (
    "Not built yet: the final implementation of this service waits for its "
    "roadmap phase; the Studio uses the demo implementation until then."
)


class SimBenchProfileService:
    """The final ``ProfileService``: SimBench profile catalogue and mapping rules (R3).

    Not implemented yet; every method raises. Builds on the new
    ``adapters/profiles/simbench.py`` (01 §3), which does not exist yet either.
    """

    def profile_types(self, source: NetworkSource | None = None) -> list[ProfileType]:
        """Will list the SimBench profile catalogue (all profiles, or one network's)."""
        raise NotImplementedError(_NOT_BUILT)

    def preview(self, file: ExperimentFile, participant_id: str) -> Series:
        """Will load the participant's profiles, apply scaling and resolution (01 §3.4)."""
        raise NotImplementedError(_NOT_BUILT)

    def suggest_mapping(self, source: NetworkSource, rule: dict) -> list[dict]:
        """Will place participants on the network by a seeded rule (01 §3.1)."""
        raise NotImplementedError(_NOT_BUILT)

    def days(self, file: ExperimentFile) -> dict[str, list[str]]:
        """Will call ``experiments.models.resolve.resolve_days`` on ``file.time``."""
        raise NotImplementedError(_NOT_BUILT)

    def tariffs(self, file: ExperimentFile) -> Series:
        """Will read the DSO tariff CSVs or the synthetic generator over the window."""
        raise NotImplementedError(_NOT_BUILT)


# ---------------------------------------------------------------------- demo implementation
HOURS = list(range(24))


class DemoProfileService:
    """Demo ``ProfileService``: generated sample curves. Shown as DEMO DATA in the
    Studio.
    """

    def profile_types(self, source: NetworkSource | None = None) -> list[ProfileType]:
        """Sample-data version of ``ProfileService.profile_types``."""
        return (
            [
                ProfileType(
                    code=f"H0-{c}", category="household", description="Household"
                )
                for c in "ABCDEFGHIJKL"
            ]
            + [
                ProfileType(
                    code=f"G{i}-A", category="commercial", description="Commercial"
                )
                for i in range(7)
            ]
            + [
                ProfileType(
                    code=f"L{i}-A", category="agricultural", description="Agricultural"
                )
                for i in range(3)
            ]
            + [
                ProfileType(code=f"PV{i}", category="pv", description="Photovoltaic")
                for i in range(1, 9)
            ]
            + [
                ProfileType(code="WP4", category="wind", description="Wind"),
                ProfileType(code="BM1", category="biomass", description="Biomass"),
            ]
        )

    def preview(self, file: ExperimentFile, participant_id: str) -> Series:
        """Sample-data version of ``ProfileService.preview``."""
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
        """Sample-data version of ``ProfileService.suggest_mapping``."""
        return _participants(int(rule.get("n", 8)))

    def days(self, file: ExperimentFile) -> dict[str, list[str]]:
        """Sample-data version of ``ProfileService.days``."""
        start = datetime(2016, 5, 2)
        days = [
            (start + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(0, 120)
            if (start + timedelta(days=i)).weekday() < 5
        ]
        cut = int(len(days) * 0.8)
        return {"train": days[:cut], "eval": days[cut:]}

    def tariffs(self, file: ExperimentFile) -> Series:
        """Sample-data version of ``ProfileService.tariffs``."""
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
