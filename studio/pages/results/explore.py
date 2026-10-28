"""Results → Explore: any recorded number of the ticked runs, with every control.

Three tables, one card each: every amount per played day, every amount per
participant, and every learner metric. Pick the metric, the phase (during
training or the test days), what a line stands for and the policy. The charts
follow the live view.
"""

from __future__ import annotations

from typing import Any

from studio.components.run_table import labels_of
from studio.pages.results.common import BY, Tab, metric_card

PHASES = {"evaluation": "During training", "heldout": "Test days"}


class ExploreTab(Tab):
    """Every metric of the per-day, per-participant and learner tables."""

    label, icon = "Explore", "explore"

    def read(self, keys: list[str]) -> dict[str, Any]:
        s = self.service
        learner = s.learner_metrics(keys)

        if not learner.empty:
            learner = learner[learner.part == ""]  # the parts: Learning tab

        return {
            "days": s.day_metrics(keys),
            "people": s.participant_metrics(keys),
            "learner": learner,
        }

    def build(self, keys: list[str], data: dict[str, Any]) -> None:
        labels = labels_of(keys)

        for title, caption, name, by in (
            ("Per day", "Every amount of a played day", "days", BY),
            (
                "Per participant",
                "Every amount of a participant on a played day",
                "people",
                BY | {"agent": "Participant"},
            ),
        ):
            metric_card(
                self,
                title,
                caption,
                name,
                data,
                labels,
                by=by,
                phases=PHASES,
                phase="evaluation",
            )

        learner_by = {k: v for k, v in BY.items() if k != "policy"}
        metric_card(
            self,
            "Learner",
            "Every learner metric over environment steps, the mean over modules "
            "(with 'A line per: Module' one line each)",
            "learner",
            data,
            labels,
            by=learner_by | {"module": "Module"},
        )
