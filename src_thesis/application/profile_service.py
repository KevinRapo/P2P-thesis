"""ProfileService: profiles and participant mapping (04 §5).

``profile_types`` and ``profile_series`` read the network's real SimBench profiles
(the Grid page's profile inspector). The other methods still return generated
sample data; each docstring says what the final version will do (R3, 01 §3).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
import src_thesis.marketplace.grid.contract_new as contract
from src_thesis.adapters.grid import simbench_new as adapter
from src_thesis.application.models import (
    ExperimentFile,
    NetworkSource,
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


_DESCRIPTIONS = {
    "household": "Household",
    "commercial": "Commercial",
    "agricultural": "Agricultural",
    "pv": "Photovoltaic",
    "wind": "Wind",
    "biomass": "Biomass",
    "storage": "Storage",
    "other": "",
}


def _category(name: str, table: str) -> str:
    """Category of a SimBench profile from its name (H0 household, G commercial…)."""
    if table == "storage":
        return "storage"
    for prefix, category in (
        ("H", "household"),
        ("G", "commercial"),
        ("L", "agricultural"),
        ("PV", "pv"),
        ("WP", "wind"),
        ("BM", "biomass"),
    ):
        if name.upper().startswith(prefix):
            return category
    return "other"


class ProfileService:
    """Generation and demand profiles and how participants map onto a network (R3).

    Every method returns sample data until it is built; its docstring says what the
    final version will do.
    """

    SAMPLE_DATA = True  # shown in the Studio's header until the service is built

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
                description=_DESCRIPTIONS.get(_category(r.name, r.table), ""),
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
