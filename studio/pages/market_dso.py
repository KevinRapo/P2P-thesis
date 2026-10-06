"""Market & DSO: clearing mechanism, bounds, tariffs and fees."""

from __future__ import annotations

from studio.components.cards import placeholder
from studio.layout import shell


def page() -> None:
    """Writes ``scenario.market`` and ``scenario.dso``."""
    with shell(
        "market",
        "Market & DSO",
        "Clearing mechanism, price and quantity bounds, DSO tariffs and fees.",
    ):
        placeholder("Not built yet.")
