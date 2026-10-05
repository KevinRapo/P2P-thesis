"""From settlement to what the grid sees: power at each participant's bus.

The grid sees physical flows, never orders or trades: an agent's production
(generation plus battery discharge) and consumption (demand plus battery
charge) over the step, as power. Energy per step becomes power with the step
length, in one place (``to_kw``).
"""

from __future__ import annotations

from typing import Iterable

from src_thesis.marlem.core.engine import Settlement
from src_thesis.marlem.grid.contract import ParticipantInjection


def to_kw(energy_kwh: float, step_hours: float) -> float:
    """Average power over a step that moved ``energy_kwh``."""
    return energy_kwh / step_hours


def injections(
    settlements: Iterable[Settlement], step_hours: float
) -> list[ParticipantInjection]:
    """The participants' injections for one power flow.

    Args:
        settlements: One per agent, from ``market.settlement.settle``.
        step_hours: Hours the step lasts.
    """
    out = []
    for s in settlements:
        production = to_kw(s.production_kwh, step_hours)
        consumption = to_kw(s.consumption_kwh, step_hours)
        out.append(
            ParticipantInjection(
                s.agent_id, s.bus, production, consumption, production - consumption
            )
        )
    return out
