"""MarketEnv: the local energy market as a multi-agent RLlib environment.

One agent per scenario participant. An episode is one market day; one step is one
market step (24 hourly or 96 quarter-hourly). The environment only translates: it
turns the agents' actions into ``OrderIntent`` s, lets ``LocalEnergyMarket`` play
the step, and turns the step's record back into observations and rewards. No
market rule lives here (``core/market/`` stays the one place for those).

Observation (``OBS_NAMES``, one vector per agent, values clipped to [-10, 10]),
computed for the step about to be played, t = ``market.current_step``. E is
``energy_scale`` (kWh) and N the number of agents:

    time          hour_sin, hour_cos: sin and cos of 2π · t / n_steps
    own profile   generation, demand, net: G_t / E, D_t / E, (G_t − D_t) / E
    own battery   has_battery (1 or 0); soc: energy as a share of its usable range
                  [min_soc, max_soc] · capacity (0 without a battery); chargeable,
                  dischargeable: what it can still take or give ([P1] eq. 15c-d),
                  divided by E
    market        reputation: the agent's own (eq. 12); price_ref: the last
                  clearing price, (p_ref − FiT) / (utility − FiT)
    last step     last_p2p, last_dso, last_balance: energy traded between peers,
                  with the DSO, and B_grid (eq. 20), divided by E · N;
                  last_reward; last_traded: (bought − sold) / E. All 0 at t = 0

The agent sees its own profile for the step it is bidding on, but nothing of the
other agents' profiles or orders, only the market totals of the last step.

Action (one vector of two numbers in [-1, 1] per agent):

    a[0]  signed quantity. |a0| < 0.05 is a dead zone: no order. a0 > 0 sells
          (a0 − 0.05) / 0.95 · max_sell_kwh, a0 < 0 buys (|a0| − 0.05) / 0.95 ·
          max_buy_kwh, the bounds of eq. 15a-b. So a0 = 1 offers all it may and
          the policy needs no knowledge of the bounds. No order below 1e-9 kWh.
    a[1]  price, FiT + (a1 + 1) / 2 · (utility − FiT): −1 is the feed-in tariff,
          +1 the utility price (the range the DSO makes every trade worth).

An agent missing from the action dict places no order.

Reward, per agent and step: the net energy bill, scaled,

    r = (profit − p_utility · deferred_demand) / reward_scale

``profit`` is eq. 14 for the step (revenue − cost of its trades − its grid fees).
``deferred_demand`` is the demand that generation, purchases and battery left
uncovered; it is drawn from the upstream grid untraded. Settlement leaves that
energy unpriced, so profit alone would make not buying free: an agent that
orders nothing would pay nothing for its imports, while one that buys pays for
them. The untraded import is therefore charged at the utility price, what the
DSO would have charged for it. Untraded exports (``deferred_supply``) earn
nothing: the surplus is spilled. Buying and selling then only pay off against
these two outside options.

Scales. ``energy_scale`` E defaults to the largest generation or demand of any
participant in any step of any day in ``days``; ``reward_scale`` defaults to
``p_utility · E``, the bill for E kWh bought from the DSO, so a reward of −1 is
one such purchase.

Episodes. ``reset`` draws a day from ``days`` and rebuilds the market (changing
the day and resetting is cheap; the first reset of a process loads the SimBench
network). The day ends the episode: ``terminateds`` is True for every agent and
``__all__`` after the last step, ``truncateds`` is always False. The end of the
day is not a cut in an endless task but the real end, and the hour is in the
observation, so the value of a state near the end is learnable and no bootstrap
is needed.

Baselines (``zero_policy``, ``net_position_policy``) map an observation dict to
an action dict, for a reference return and for tests.

``env_config`` keys (JSON-serialisable, so RLlib can pass it to its workers):

    scenario      path to a scenario JSON (required)
    days          days ``"YYYY-MM-DD"`` to draw from at each reset (default: the
                  scenario's day)
    energy_scale  E in kWh (default: computed from ``days``)
    reward_scale  default ``p_utility · E``
    seed          seed of the day draw for the first reset
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
from gymnasium import spaces
from ray.rllib.env.multi_agent_env import MultiAgentEnv

from core.config import store
from core.market.lem import LocalEnergyMarket, OrderIntent, StepRecord

# --------------------------------------------------------------------------------------
# What the agents see
# --------------------------------------------------------------------------------------
OBS_NAMES: tuple[str, ...] = (
    "hour_sin",
    "hour_cos",
    "generation",
    "demand",
    "net",
    "has_battery",
    "soc",
    "chargeable",
    "dischargeable",
    "reputation",
    "price_ref",
    "last_p2p",
    "last_dso",
    "last_balance",
    "last_reward",
    "last_traded",
)
_OBS_LIMIT = 10.0
_DEAD_ZONE = 0.05  # |a0| below this places no order
_MIN_ORDER_KWH = 1e-9


# --------------------------------------------------------------------------------------
# The environment
# --------------------------------------------------------------------------------------
class MarketEnv(MultiAgentEnv):
    """The local energy market, one agent per participant (see the module docstring).

    Args:
        env_config: ``scenario`` (path, required), ``days``, ``energy_scale``,
            ``reward_scale``, ``seed``.
    """

    def __init__(self, env_config: Optional[dict[str, Any]] = None) -> None:
        super().__init__()
        config = env_config or {}
        if "scenario" not in config:
            raise ValueError("env_config needs 'scenario': the path of a scenario JSON")
        scenario = store.load(Path(config["scenario"]))
        self.market = LocalEnergyMarket(scenario)
        self.days: list[str] = list(config.get("days") or [scenario.grid.day])
        self.agents_id: list[str] = [p.id for p in scenario.participants]
        self.agents = self.possible_agents = list(self.agents_id)
        self.feed_in_tariff = scenario.dso.feed_in_tariff
        self.utility_price = scenario.dso.utility_price
        self.energy_scale: float = float(
            config.get("energy_scale") or self._largest_energy()
        )
        self.reward_scale: float = float(
            config.get("reward_scale") or self.utility_price * self.energy_scale
        )
        obs_box = spaces.Box(-_OBS_LIMIT, _OBS_LIMIT, (len(OBS_NAMES),), np.float32)
        act_box = spaces.Box(-1.0, 1.0, (2,), np.float32)
        self.observation_spaces = {a: obs_box for a in self.agents_id}
        self.action_spaces = {a: act_box for a in self.agents_id}
        self.rng = np.random.default_rng(config.get("seed"))
        self.last_record: Optional[StepRecord] = None
        self._clear_memory()

    def _largest_energy(self) -> float:
        """The largest generation or demand (kWh) of any participant in any step
        of any day in ``days``: the default ``energy_scale`` (at least 1e-6)."""
        largest = 0.0
        for day in self.days:
            self.market.scenario.grid.day = day
            self.market.reset()
            for p in self.market.participants.values():
                largest = max(largest, max(p.generation_kwh), max(p.demand_kwh))
        return max(largest, 1e-6)

    # --- Episodes --------------------------------------------------------------------
    def reset(self, *, seed: Optional[int] = None, options: Optional[dict] = None):
        """Draw a day, rebuild the market for it, return the first observations
        and ``{"day": day}`` per agent."""
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        day = self.days[int(self.rng.integers(len(self.days)))]
        self.market.scenario.grid.day = day
        self.market.reset()
        self.last_record = None
        self._clear_memory()
        infos = {a: {"day": day} for a in self.agents_id}
        return self._observe(), infos

    def step(self, action_dict: dict[str, np.ndarray]):
        """Play one market step with the agents' orders."""
        intents = {}
        for pid, action in action_dict.items():
            intent = self.decode(pid, action)
            if intent is not None:
                intents[pid] = intent
        record = self.market.step(intents)
        self.last_record = record

        rewards, infos = {}, {}
        for pid in self.agents_id:
            o = record.participants[pid]
            bill = o.profit - self.utility_price * o.deferred_demand_kwh
            rewards[pid] = bill / self.reward_scale
            infos[pid] = {
                "profit": float(o.profit),
                "bill": float(bill),
                "bought_kwh": float(o.bought_kwh),
                "sold_kwh": float(o.sold_kwh),
                "deferred_demand_kwh": float(o.deferred_demand_kwh),
                "deferred_supply_kwh": float(o.deferred_supply_kwh),
                "p2p_kwh": float(record.p2p_kwh),
                "dso_kwh": float(record.dso_kwh),
                "clearing_price": float(record.clearing_price),
            }
        n = len(self.agents_id)
        scale = self.energy_scale * n
        self._memory = {
            "p2p": record.p2p_kwh / scale,
            "dso": record.dso_kwh / scale,
            "balance": record.grid_balance_kwh / scale,
            "reward": dict(rewards),
            "traded": {
                pid: (o.bought_kwh - o.sold_kwh) / self.energy_scale
                for pid, o in record.participants.items()
            },
        }
        done = self.market.done
        terminateds = {a: done for a in self.agents_id} | {"__all__": done}
        truncateds = {a: False for a in self.agents_id} | {"__all__": False}
        return self._observe(), rewards, terminateds, truncateds, infos

    # --- Actions ---------------------------------------------------------------------
    def decode(self, pid: str, action: np.ndarray) -> Optional[OrderIntent]:
        """The order an action means for the step about to be played (``None``: no
        order): a0 the signed quantity, a1 the price (see the module docstring)."""
        a = np.clip(np.asarray(action, dtype=np.float64).reshape(-1), -1.0, 1.0)
        if a.size < 2 or abs(a[0]) < _DEAD_ZONE:
            return None
        participant = self.market.participants[pid]
        step = self.market.current_step
        share = (abs(a[0]) - _DEAD_ZONE) / (1.0 - _DEAD_ZONE)
        is_buy = bool(a[0] < 0)
        most = (
            participant.max_buy_kwh(step) if is_buy else participant.max_sell_kwh(step)
        )
        quantity = share * most
        if quantity <= _MIN_ORDER_KWH:
            return None
        spread = self.utility_price - self.feed_in_tariff
        price = self.feed_in_tariff + (a[1] + 1.0) / 2.0 * spread
        return OrderIntent(pid, is_buy, float(price), float(quantity))

    # --- Observations ----------------------------------------------------------------
    def _clear_memory(self) -> None:
        """Forget the last step: what the observation reports of it is 0 again."""
        self._memory = {
            "p2p": 0.0,
            "dso": 0.0,
            "balance": 0.0,
            "reward": {a: 0.0 for a in self.agents_id},
            "traded": {a: 0.0 for a in self.agents_id},
        }

    def _observe(self) -> dict[str, np.ndarray]:
        """Every agent's observation for the step about to be played. After the
        last step it holds the last step's profiles with the hour at midnight
        (the episode is over; RLlib wants a final observation)."""
        m = self.market
        t = m.current_step
        scale = self.energy_scale
        angle = 2.0 * np.pi * t / m.n_steps
        spread = self.utility_price - self.feed_in_tariff
        price_ref = (m.clearing_price - self.feed_in_tariff) / spread
        out = {}
        for pid in self.agents_id:
            p = m.participants[pid]
            k = min(t, m.n_steps - 1)
            g, d = p.generation_kwh[k], p.demand_kwh[k]
            chargeable, dischargeable = p.battery_room()
            b = p.battery
            soc = (b.energy_kwh - b.min_kwh) / (b.max_kwh - b.min_kwh) if b else 0.0
            values = (
                np.sin(angle),
                np.cos(angle),
                g / scale,
                d / scale,
                (g - d) / scale,
                1.0 if b else 0.0,
                soc,
                chargeable / scale,
                dischargeable / scale,
                p.reputation,
                price_ref,
                self._memory["p2p"],
                self._memory["dso"],
                self._memory["balance"],
                self._memory["reward"][pid],
                self._memory["traded"][pid],
            )
            out[pid] = np.clip(
                np.array(values, dtype=np.float32), -_OBS_LIMIT, _OBS_LIMIT
            )
        return out


# --------------------------------------------------------------------------------------
# Baseline policies: functions of the observation dict
# --------------------------------------------------------------------------------------
def zero_policy(env: MarketEnv) -> Callable[[dict[str, np.ndarray]], dict]:
    """No orders: every agent sends the zero action (inside the dead zone)."""
    agents = list(env.agents_id)
    return lambda obs: {a: np.zeros(2, dtype=np.float32) for a in agents}


def net_position_policy(
    env: MarketEnv, margin: float = 0.3, battery_first: bool = True
) -> Callable[[dict[str, np.ndarray]], dict]:
    """The market's own bidding rule (``core/market/bidding.py``) read from the
    observation: a surplus is offered at ``FiT + margin · spread``, a deficit asked
    for at ``utility − margin · spread``, without the rule's jitter.

    With ``battery_first`` (the rule's) the battery takes what it can first, so
    the order is ``net − min(net, chargeable)`` when selling and
    ``−net − min(−net, dischargeable)`` when buying. Without it the agent offers
    its whole surplus or asks for its whole deficit.
    """
    agents = list(env.agents_id)
    index = {name: i for i, name in enumerate(OBS_NAMES)}

    def policy(obs: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        actions = {}
        for pid in agents:
            o = obs[pid]
            net = float(o[index["net"]])
            chargeable = float(o[index["chargeable"]])
            dischargeable = float(o[index["dischargeable"]])
            action = np.zeros(2, dtype=np.float32)
            share = 0.0
            if net > _MIN_ORDER_KWH:
                kept = min(net, chargeable) if battery_first else 0.0
                share = (net - kept) / (net + dischargeable)
                action[0] = _DEAD_ZONE + (1.0 - _DEAD_ZONE) * share
                action[1] = 2.0 * margin - 1.0
            elif net < -_MIN_ORDER_KWH:
                kept = min(-net, dischargeable) if battery_first else 0.0
                share = (-net - kept) / (-net + chargeable)
                action[0] = -(_DEAD_ZONE + (1.0 - _DEAD_ZONE) * share)
                action[1] = 1.0 - 2.0 * margin
            if share <= _MIN_ORDER_KWH:
                action[0] = 0.0  # nothing left to trade: no order
            actions[pid] = action
        return actions

    return policy
