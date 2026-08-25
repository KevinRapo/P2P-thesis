"""Application service used by all NiceGUI pages."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .domain import GridResult, GridScenario, IllustrativeGridModel


@dataclass(frozen=True)
class RunSnapshot:
    run_id: str
    created_at: str
    result: GridResult

    def as_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "result": self.result.as_dict(),
        }


class StudioService:
    """In-memory run service with an explicit JSON export boundary."""

    def __init__(self, model: IllustrativeGridModel | None = None) -> None:
        self.model = model or IllustrativeGridModel()
        self.history: list[RunSnapshot] = []

    @property
    def latest(self) -> RunSnapshot | None:
        return self.history[-1] if self.history else None

    def run_grid(self, scenario: GridScenario) -> RunSnapshot:
        result = self.model.run(scenario)
        snapshot = RunSnapshot(
            run_id=f"demo-{len(self.history) + 1:03d}",
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            result=result,
        )
        self.history.append(snapshot)
        return snapshot

    def save_latest(self, path: Path) -> Path:
        if self.latest is None:
            raise ValueError("Run a scenario before saving a snapshot.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.latest.as_dict(), indent=2) + "\n",
            encoding="utf-8",
        )
        return path
