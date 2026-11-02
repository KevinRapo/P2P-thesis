"""Saving and loading scenarios as JSON files."""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from pathlib import Path

from core.config.scenario import (
    FLAT_PRICES,
    BatterySetup,
    DsoSetup,
    GridSetup,
    MarketSetup,
    ParticipantSetup,
    Scenario,
)


def _known(cls: type, data: dict) -> dict:
    """The keys of ``data`` that ``cls`` has; others (from older files) are dropped."""
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in names}


def from_dict(data: dict) -> Scenario:
    """A scenario from its JSON form."""
    participants = []

    for p in data.get("participants", []):
        values = _known(ParticipantSetup, p)
        battery = values.pop("battery", None)

        if battery:
            values["battery"] = BatterySetup(**_known(BatterySetup, battery))

        participants.append(ParticipantSetup(**values))

    return Scenario(
        name=data.get("name", "untitled"),
        grid=GridSetup(**_known(GridSetup, data.get("grid", {}))),
        participants=participants,
        market=MarketSetup(**_known(MarketSetup, data.get("market", {}))),
        dso=_dso(data.get("dso", {})),
    )


def _dso(data: dict) -> DsoSetup:
    """The DSO of a saved scenario. An older file without a price series has its flat
    tariffs in two fields of their own, and ``prices`` null."""
    values = _known(DsoSetup, data)

    if values.get("prices") is None:
        values["prices"] = {
            "utility": data.get("utility_price", FLAT_PRICES["utility"]),
            "feed_in": data.get("feed_in_tariff", FLAT_PRICES["feed_in"]),
        }

    return DsoSetup(**values)


def load(path: Path) -> Scenario:
    """The scenario saved at ``path``."""
    return from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def save(scenario: Scenario, path: Path) -> None:
    """Write ``scenario`` to ``path``, with Unix line endings on every platform so a
    saved scenario does not show as changed in git after each save on Windows."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(asdict(scenario), indent=2)
    path.write_text(text, encoding="utf-8", newline="\n")
