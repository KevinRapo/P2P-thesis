"""Step: play the configured market one step at a time and watch the network."""

from __future__ import annotations

from studio.components.cards import placeholder
from studio.layout import shell


def page() -> None:
    """Reset / Step / Run to end; network plot coloured by the power flow;
    orders, trades and participant outcomes of the current step."""
    with shell(
        "step",
        "Step",
        "Play the market one step at a time; each step runs a power flow.",
    ):
        placeholder("Not built yet.")
