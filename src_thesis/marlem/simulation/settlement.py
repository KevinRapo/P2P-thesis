"""Settlement: what each agent physically and financially did in one step.

Built from the step's outcome (orders, trades, battery energy), never from the
orders alone (01 §5). Trades move energy on paper; the physical flows at an
agent's bus are its generation, demand and battery. The part of that net flow
that no trade covers is the agent's exchange with the upstream grid.
"""

from __future__ import annotations

from src_thesis.marlem.simulation.spec import EngineSpec, Settlement, StepOutcome


def settle(outcome: StepOutcome, spec: EngineSpec) -> dict[str, Settlement]:
    """One ``Settlement`` per agent for one step.

    The battery's energy change gives its grid-side flow: charging draws
    ``delta / charge_efficiency`` from the bus, discharging delivers
    ``-delta * discharge_efficiency`` to it.

    Args:
        outcome: What the engine reported for the step.
        spec: The world, for each agent's bus and battery efficiencies.
    """
    sold = {a.id: 0.0 for a in spec.agents}
    bought = {a.id: 0.0 for a in spec.agents}
    for trade in outcome.trades:
        if trade["seller_id"] in sold:
            sold[trade["seller_id"]] += trade["quantity_kwh"]
        if trade["buyer_id"] in bought:
            bought[trade["buyer_id"]] += trade["quantity_kwh"]
    out = {}
    for agent in spec.agents:
        before = outcome.soc_before_kwh.get(agent.id)
        after = outcome.soc_after_kwh.get(agent.id)
        delta = 0.0 if before is None or after is None else after - before
        charge = discharge = 0.0
        if agent.battery is not None:
            if delta > 0:
                charge = delta / agent.battery.charge_efficiency
            else:
                discharge = -delta * agent.battery.discharge_efficiency
        generation = outcome.generation_kwh[agent.id]
        demand = outcome.demand_kwh[agent.id]
        production = generation + discharge
        consumption = demand + charge
        out[agent.id] = Settlement(
            agent_id=agent.id,
            bus=agent.bus,
            generation_kwh=generation,
            demand_kwh=demand,
            sold_kwh=sold[agent.id],
            bought_kwh=bought[agent.id],
            charge_kwh=charge,
            discharge_kwh=discharge,
            soc_delta_kwh=delta,
            production_kwh=production,
            consumption_kwh=consumption,
            external_kwh=(production - consumption)
            - (sold[agent.id] - bought[agent.id]),
            soc_kwh=after,
        )
    return out
