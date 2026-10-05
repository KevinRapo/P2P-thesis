"""``LocalEnergyMarket`` behind the ``MarketEngine`` interface.

The original environment stays as it is, faults included. This adapter feeds it
the profiles of an ``EngineSpec`` (I-05), runs all steps of the day (I-01),
copies the raw actions and the batteries' energy before and after each step
(I-12 and I-18 stay visible), and reports plain data. Intents are translated to
the environment's action format: the environment sizes an order by what is left
after own generation, demand and battery (I-08), so an order of ``Q`` kWh is asked
for as ``Q`` plus what the environment will take off again.
"""

from __future__ import annotations

from typing import Mapping, Optional

import numpy as np

from src_thesis.marlem.agents.battery import Battery
from src_thesis.marlem.agents.der import DERAgent
from src_thesis.marlem.simulation.spec import (
    AgentSpec,
    EngineSpec,
    MarketEngine,
    StepOutcome,
)
from src_thesis.marlem.core.location import GridTopology
from src_thesis.marlem.simulation.policy import AgentView, Intent
from src_thesis.marlem.dso.dso import DSOAgent
from src_thesis.marlem.environment.lem import LocalEnergyMarket
from src_thesis.marlem.grid.network import GridNetwork
from src_thesis.marlem.market.matching import ClearingMechanism, MarketConfig
from src_thesis.marlem.profiles.dso import DSOProfileHandler
from src_thesis.marlem.simulation.fixed_profiles import FixedProfileHandler


def _padded(
    values: list[float],
    length: int,
    low: float = float("-inf"),
    high: float = float("inf"),
) -> list[float]:
    """``values`` cut or extended (repeating the last value) to ``length`` and
    limited to ``[low, high]``."""
    values = list(values)[:length]
    values += [values[-1]] * (length - len(values))
    return [min(high, max(low, v)) for v in values]


class LemEngine:
    """The original market as a ``MarketEngine``.

    Args:
        spec: The world to run.
        grid: Grid view for matching distances and fees; a placeholder mesh of
            the agents when ``None``.
    """

    def __init__(self, spec: EngineSpec, grid: Optional[object] = None) -> None:
        self.spec = spec
        self.agent_ids = [a.id for a in spec.agents]
        self.n_steps = spec.steps
        self.step_hours = spec.step_hours
        self.warnings = list(spec.warnings)
        # DEVIATION I-01: the environment stops one step early, so one extra
        # step is configured and never played.
        self._max_steps = spec.steps + 1
        market = spec.market
        self._market = market
        bounds = (market.min_quantity, market.max_quantity)
        self._config = MarketConfig(
            min_price=market.min_price,
            max_price=market.max_price,
            min_quantity=market.min_quantity,
            max_quantity=market.max_quantity,
            price_mechanism=ClearingMechanism(market.mechanism),
            blockchain_difficulty=max(1, market.ledger_difficulty),
            enable_partner_preference=market.partner_preference,
            _threshold=market.match_threshold,
        )
        profiles = [
            (
                _padded(a.generation_kwh, self._max_steps, *bounds),
                _padded(a.demand_kwh, self._max_steps, *bounds),
            )
            for a in spec.agents
        ]
        self._fixed = FixedProfileHandler(
            profiles, market.min_quantity, market.max_quantity
        )
        # Bus names only mean something to a real grid view; the placeholder mesh
        # has its own nodes.
        agents = [
            self._agent(a, g, d, a.bus if grid is not None else None)
            for a, (g, d) in zip(spec.agents, profiles)
        ]
        capacity = max(1.0, sum(a.capacity_kwh for a in spec.agents))
        network = grid or GridNetwork(
            GridTopology.MESH, len(agents), capacity, seed=spec.seed
        )
        csv = spec.tariffs.source == "csv"
        handler = DSOProfileHandler(
            market.min_price,
            market.max_price,
            spec.tariffs.feed_in_path if csv else None,
            spec.tariffs.utility_path if csv else None,
            seed=spec.seed,
        )
        fit, utility = handler.get_price_profiles(self._max_steps)
        dso = DSOAgent(
            "DSO",
            _padded(fit, self._max_steps),
            _padded(utility, self._max_steps),
            network,
        )
        for name, value in spec.fees.items():
            if hasattr(dso, name):
                setattr(dso, name, float(value))
        self.env = LocalEnergyMarket(
            {
                "max_steps": self._max_steps,
                "market_config": self._config,
                "grid_network": network,
                "dso": dso,
                "der_profile_handler": self._fixed,
                "dso_profile_handler": handler,
                "agents": agents,
                "enable_asynchronous_order": market.async_orders,
                "seed": spec.seed,
            }
        )

    @staticmethod
    def _agent(
        a: AgentSpec,
        generation: list[float],
        demand: list[float],
        node: Optional[str],
    ) -> DERAgent:
        battery = None
        if a.battery is not None:
            b = a.battery
            battery = Battery(
                b.capacity_kwh,
                b.min_soc,
                b.max_soc,
                b.charge_efficiency,
                b.discharge_efficiency,
            )
        return DERAgent(a.id, a.capacity_kwh, battery, node, generation, demand)

    def reset(self, seed: int) -> None:
        """Start the day: profiles and batteries as specified, market empty."""
        self._fixed.rewind()
        self.env.reset(seed=seed)
        for spec in self.spec.agents:
            agent = self.env._agents[spec.id]
            agent.balance = 0.0
            if spec.battery is not None:
                b = spec.battery
                soc = b.initial_soc
                if soc is None:
                    soc = (b.min_soc + b.max_soc) / 2
                agent.battery.energy_level = soc * b.capacity_kwh

    def views(self) -> dict[str, AgentView]:
        """What each agent can see at the current step."""
        step = self.env.current_step
        dso = self.env.dso
        out = {}
        for spec in self.spec.agents:
            agent = self.env._agents[spec.id]
            battery = agent.battery
            charge, discharge = (
                battery.estimate_available_energy() if battery else (0.0, 0.0)
            )
            out[spec.id] = AgentView(
                agent_id=spec.id,
                step=step,
                generation_kwh=float(agent.get_generation(step)),
                demand_kwh=float(agent.get_demand(step)),
                fit=float(dso.get_feed_in_tariff(step)),
                utility_price=float(dso.get_utility_price(step)),
                min_price=self._market.min_price,
                max_price=self._market.max_price,
                min_quantity=self._market.min_quantity,
                max_quantity=min(self._market.max_quantity, spec.capacity_kwh),
                soc_kwh=float(battery.energy_level) if battery else None,
                battery_available_charge=float(charge),
                battery_available_discharge=float(discharge),
            )
        return out

    @staticmethod
    def _action(view: AgentView, intent: Intent) -> np.ndarray:
        """The environment's action vector for an intent."""
        quantity = min(intent.quantity_kwh, view.max_quantity)
        if intent.is_buy:
            quantity += view.generation_kwh + view.battery_available_discharge
        else:
            quantity += view.demand_kwh + view.battery_available_charge
        return np.array(
            [intent.price, quantity, 1.0 if intent.is_buy else 0.0, 0.0],
            dtype=np.float32,
        )

    def _energy(self) -> dict[str, Optional[float]]:
        return {
            i: (float(a.battery.energy_level) if a.battery else None)
            for i, a in self.env._agents.items()
        }

    def step(self, intents: Mapping[str, Intent]) -> StepOutcome:
        """Play one step."""
        env = self.env
        step = env.current_step
        views = self.views()
        before = self._energy()
        actions = {
            i: self._action(
                views[i], intents.get(i, Intent.nothing(views[i].min_price))
            )
            for i in self.agent_ids
        }
        env.step(actions)  # adjusts ``actions`` in place
        m = self._market
        orders = []
        for i in self.agent_ids:
            price, quantity, is_buy, _ = actions[i]
            orders.append(
                {
                    "agent_id": i,
                    "price": float(max(m.min_price, min(m.max_price, price))),
                    "quantity_kwh": float(
                        max(m.min_quantity, min(views[i].max_quantity, quantity))
                    ),
                    "is_buy": bool(is_buy > 0.5),
                }
            )
        trades = [
            {
                "buyer_id": t.buyer_id,
                "seller_id": t.seller_id,
                "price": float(t.price),
                "quantity_kwh": float(t.quantity),
                "distance": float(t.distance),
                "loss_kwh": float(t.transmission_loss),
                "fees": float(t.fees),
            }
            for t in env.info["trades"]
        ]
        stats = env.info["dso_stats"]
        first = views[self.agent_ids[0]]
        return StepOutcome(
            step=step,
            orders=orders,
            trades=trades,
            generation_kwh={i: v.generation_kwh for i, v in views.items()},
            demand_kwh={i: v.demand_kwh for i, v in views.items()},
            soc_before_kwh=before,
            soc_after_kwh=self._energy(),
            fit=first.fit,
            utility_price=first.utility_price,
            clearing_price=float(env.info["market_price"] or 0.0),
            p2p_kwh=float(stats["p2p_volume"]),
            dso_kwh=float(stats["dso_total_volume"]),
        )


def build_engine(spec: EngineSpec, grid: Optional[object] = None) -> MarketEngine:
    """The engine for ``spec`` (today always the original ``LocalEnergyMarket``)."""
    return LemEngine(spec, grid)
