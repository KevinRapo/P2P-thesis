"""The reward: what a played market step is worth to each agent.

``MarketEnv.step`` calls this file with the step's record. It holds no market rule
(``core/market/`` stays the one place for those) and changes nothing: it only reads
what the market did.

Reward, per agent and step: the net energy bill, scaled,

    r = (profit − p_utility · deferred_demand) / reward_scale

``profit`` is eq. 14 for the step (revenue − cost of its trades − its grid fees);
p_utility is the step's (time-of-use tariffs change by hour).
``deferred_demand`` is the demand that generation, purchases and battery left
uncovered; it is drawn from the upstream grid untraded. Settlement leaves that
energy unpriced, so profit alone would make not buying free: an agent that
orders nothing would pay nothing for its imports, while one that buys pays for
them. The untraded import is therefore charged at the utility price, what the
DSO would have charged for it. Untraded exports (``deferred_supply``) earn
nothing: the surplus is spilled. Buying and selling then only pay off against
these two outside options.

With ``terminal_value`` (``MarketEnv``) the window's last reward adds the change of
the stored energy at ``stored_kwh_value`` per kWh.
"""

from __future__ import annotations

from core.market.lem import StepRecord


def net_bill(record: StepRecord, pid: str) -> float:
    """Agent ``pid``'s net bill for the step, in the scenario's money unit."""
    outcome = record.participants[pid]

    return outcome.profit - record.inputs.utility_price * outcome.deferred_demand_kwh


def step_rewards(record: StepRecord, reward_scale: float) -> dict[str, float]:
    """Every agent's reward for the step."""
    return {pid: net_bill(record, pid) / reward_scale for pid in record.participants}


def terminal_reward(
    gain_kwh: float, stored_kwh_value: float, reward_scale: float
) -> float:
    """What the window's last reward adds for ``gain_kwh`` more energy stored."""
    return stored_kwh_value * gain_kwh / reward_scale
