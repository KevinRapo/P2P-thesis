"""ProfileService: profiles and participant mapping (04 §5).

Every method still returns generated sample data; each docstring says what the
final version will do. It builds on the SimBench profile source of 01 §3 (R3).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
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


class ProfileService:
    """Generation and demand profiles and how participants map onto a network (R3).

    Every method returns sample data until it is built; its docstring says what the
    final version will do.
    """

    SAMPLE_DATA = True  # shown in the Studio's header until the service is built

    def profile_types(self, source: NetworkSource | None = None) -> list[ProfileType]:
        """Profile types that can be assigned (SimBench catalogue).

        Sample data for now. The final version will list the SimBench profile catalogue
        (all profiles, or one network's).
        """
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
