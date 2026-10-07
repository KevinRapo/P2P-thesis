"""Saving and loading scenarios as JSON files."""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from pathlib import Path

from config.scenario import (
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
        dso=DsoSetup(**_known(DsoSetup, data.get("dso", {}))),
    )


def load(path: Path) -> Scenario:
    """The scenario saved at ``path``."""
    return from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def save(scenario: Scenario, path: Path) -> None:
    """Write ``scenario`` to ``path``."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(scenario), indent=2), encoding="utf-8")
