"""Grid & Participants: pick the network, place the participants on its buses."""

from __future__ import annotations

from studio.components.cards import placeholder
from studio.layout import shell


def page() -> None:
    """Writes ``scenario.grid`` and ``scenario.participants``."""
    with shell(
        "grid",
        "Grid & Participants",
        "Pick the network and place the participants on its buses.",
    ):
        placeholder("Not built yet.")
