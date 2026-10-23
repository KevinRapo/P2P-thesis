"""MarketEnv: the local energy market as a multi-agent RLlib environment.

One agent per scenario participant. An episode is one market day; one step is one
market step (24 hourly or 96 quarter-hourly). The environment only translates: it
turns the agents' actions into ``OrderIntent`` s, lets ``LocalEnergyMarket`` play
the step, and turns the step's record back into observations and rewards. No
market rule lives here (``core/market/`` stays the one place for those).

Observation (``obs_names``, one vector per agent, values clipped to [-10, 10]),
computed for the step about to be played, t = ``market.current_step``. E is
``energy_scale`` (kWh) and N the number of agents. The first 16 entries are V1's
(``OBS_NAMES``):

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

V2 adds what the partner choice needs (``PARTNER_OBS``), in the agent's candidate
order (below):

    last_preference      energy the agent traded in stage 1 (mutual preferences)
                         in the last step, bought + sold, / E; 0 at t = 0. Its own
                         outcome, known after that step.
    partner_rep_k        candidate k's reputation (eq. 12) after the last step, for
                         the N − 1 other participants. Public: the paper adds every
                         agent's reputation to the observation when partner
                         preference is on ([P1] Table 2), and the auction ranks by
                         it.
    partner_dist_k       grid distance d_ij to candidate k ([P1] §3.5.1, the market's
                         ``distance_km``), and partner_dist_dso to the transformer,
                         divided by the largest such distance in the network
                         (``distance_scale``). Topology, the same on every day.

The agent sees its own profile and battery for the step it is bidding on, the
public reputations and the topology, but nothing of the other agents' profiles,
batteries or current orders: the orders of the step are submitted at the same
time and seen by nobody before clearing. DTDE and CTDE give each agent this same
local observation (CTDE's critic adds the others', ``core/rl/ctde.py``).

Action: the paper's a_i = <p_bid, q_bid, α, β> ([P1] eq. 2) as a ``Dict`` of four
components (``ACTION_COMPONENTS``), two continuous and two categorical:

    side      Discrete(2): α, 0 sell, 1 buy
    quantity  Box([-1, 1]): q_bid as a share of what the agent may sell or buy this
              step (eq. 15a-b): share = (q + 1) / 2. Below ``NO_ORDER_SHARE`` (0.05)
              there is no order; above it the share is rescaled to (0, 1] of the
              bound, so q = 1 offers all it may and the policy needs no knowledge
              of the bounds. No order below 1e-9 kWh.
    price     Box([-1, 1]): p_bid = FiT + (p + 1) / 2 · (utility − FiT): −1 is the
              feed-in tariff, +1 the utility price (the range the DSO makes every
              trade worth)
    partner   Discrete(N + 1): β, an index into the agent's candidates
              (``partners(agent)``): the N − 1 other participants in scenario
              order, then the DSO, then "no preference"

What is the paper's and what is an encoding choice made here: the four components
and their kinds (price and quantity continuous, side and partner categorical) are
[P1] eq. 2. The quantity as a share of the eq. 15 bound, the no-order threshold,
the price range and the candidate order are this implementation's encoding. The
chosen partner goes into ``OrderIntent.partner_id`` as it is, "no preference"
included (None): the scenario's rule-based partner choice
(``market.partner_preference``) is never applied to an RL agent's order. Stage 1
of the clearing pairs agents that named each other on opposite sides, bid ≥ ask;
an order naming the DSO waits for stage 3; every other order goes to the double
auction (``core/market/clearing.py``, unchanged).

Under RLlib the policy is factorised over the components (one distribution each,
``core/rl``): the partner is not conditioned on the sampled side or price.

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
one such purchase. A run resolves both once, on its training days, and keeps them
(``resolved_config``): validation, the held-out days and a restored policy use
the training values, so an observation and a reward mean the same everywhere.

Episodes. ``reset`` draws a day from ``days`` (or plays ``options["day"]``, one
of them: the held-out evaluation plays each test day once) and rebuilds the market
for it (changing the day and resetting is cheap; the first reset of a process
loads the SimBench network). The day ends the episode: ``terminateds`` is True for
every agent and ``__all__`` after the last step, ``truncateds`` is always False.
The end of the day is not a cut in an endless task but the real end, and the hour
is in the observation, so the value of a state near the end is learnable and no
bootstrap is needed.

Infos, per agent and step, in the layout ``core/rl/policy.py`` reads (amounts
are summed over an episode, states only kept step by step; kWh and the scenario's
money unit):

    profit, bill                   the step's profit (eq. 14) and the net bill of
                                   the reward, before scaling
    bought_kwh, sold_kwh           traded energy, peers and DSO together
    preference_kwh                 traded in stage 1 (mutual preferences)
    deferred_demand_kwh            demand drawn untraded from the upstream grid
    deferred_supply_kwh            surplus spilled untraded
    state: order_kwh               the order placed, as the market took it after
                                   validation: + sell, − buy, 0 none
           order_price             its price (NaN without an order)
           side                    "buy", "sell" or "none" (no order)
           partner                 the partner named: a participant, "DSO" or
                                   "none" (also "none" without an order)
           partner_index           the partner component's index (NaN without an
                                   order)
           partner_mutual          1 if the partner named this agent back with an
                                   order on the other side, else 0 (NaN without a
                                   peer named)
           soc                     battery state of charge after the step, 0 to 1
                                   (NaN without a battery)
           reputation              reputation after the step (eq. 12)
    shared: p2p_kwh                energy traded between participants
            preference_kwh         of it, traded in stage 1
            sold_to_dso_kwh        energy participants sold to the DSO (stage 3)
            bought_from_dso_kwh    energy participants bought from the DSO
            trade_losses_kwh       transmission losses of the trades (eq. 18)
            fees                   grid fees of the trades (eq. 8)
            grid_import_kwh        energy the network drew from the upstream grid
            grid_export_kwh        energy it fed into the upstream grid
            grid_losses_kwh        line and transformer losses of the power flow
            grid_violations        voltage and loading limits the flow broke
            not_converged          1 if the power flow did not converge
    shared_state: clearing_price   the step's clearing price
                  min_voltage_pu, max_voltage_pu, max_line_loading_percent
                  fee_max_line_loading_percent: the highest line loading the
                  fees were charged on (the graph model's with ``grid.method =
                  "graph"``, else the power flow's)

The grid amounts are the AC power flow's (the whole network, background
included), whatever ``grid.method``; a flow that did not converge counts 0 for
them.

Baselines (``zero_policy``, ``net_position_policy``) map an observation dict to
an action dict, for a reference return and for tests; ``baseline_policies``
gives both to the RL layer's evaluation.

``env_config`` keys (JSON-serialisable, so RLlib can pass it to its workers):

    scenario      path to a scenario JSON (required)
    days          days ``"YYYY-MM-DD"`` to draw from at each reset (default: the
                  scenario's day; ``reset(options={"day": ...})`` plays one of them)
    energy_scale  E in kWh (default: computed from ``days``)
    reward_scale  default ``p_utility · E``
    seed          seed of the day draw for the first reset
    grid, dso     settings that replace the scenario's (``GridSetup``, ``DsoSetup``
                  fields), e.g. ``{"grid": {"method": "graph"}}``: the arms of an
                  experiment as variants of one scenario
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
from gymnasium import spaces
from ray.rllib.env.multi_agent_env import MultiAgentEnv

from core.config import store
from core.market.dso.dso import DSO_ID
from core.market.lem import LocalEnergyMarket, OrderIntent, StepRecord
from core.market.order import Order

# --------------------------------------------------------------------------------------
# What the agents see and do
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
PARTNER_OBS = ("last_preference", "partner_rep_k", "partner_dist_k", "partner_dist_dso")
ACTION_COMPONENTS = ("side", "quantity", "price", "partner")
SIDES = ("sell", "buy")  # α: index 0 sells, 1 buys ([P1] eq. 2)
NO_PREFERENCE = "none"  # the last partner candidate: no partner named
NO_ORDER_SHARE = 0.05  # quantity share below this places no order
SCALE_KEYS = ("energy_scale", "reward_scale")
_OBS_LIMIT = 10.0
_MIN_ORDER_KWH = 1e-9


# --------------------------------------------------------------------------------------
# The environment
# --------------------------------------------------------------------------------------
class MarketEnv(MultiAgentEnv):
    """The local energy market, one agent per participant (see the module docstring).

    Args:
        env_config: ``scenario`` (path, required), ``days``, ``energy_scale``,
            ``reward_scale``, ``seed``, ``grid``, ``dso``.
    """

    def __init__(self, env_config: Optional[dict[str, Any]] = None) -> None:
        super().__init__()
        config = env_config or {}
        if "scenario" not in config:
            raise ValueError("env_config needs 'scenario': the path of a scenario JSON")
        self.config = dict(config)
        scenario = store.load(Path(config["scenario"]))
        _override(scenario.grid, config.get("grid"), "grid")
        _override(scenario.dso, config.get("dso"), "dso")
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
        self._candidates = {
            a: [b for b in self.agents_id if b != a] + [DSO_ID, None]
            for a in self.agents_id
        }
        self._distances = self._partner_distances()
        self.obs_names: tuple[str, ...] = OBS_NAMES + self._partner_names()
        obs_box = spaces.Box(
            -_OBS_LIMIT, _OBS_LIMIT, (len(self.obs_names),), np.float32
        )
        self.observation_spaces = {a: obs_box for a in self.agents_id}
        self.action_spaces = {a: self._action_space() for a in self.agents_id}
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

    def _action_space(self) -> spaces.Dict:
        """One agent's action: the four components of [P1] eq. 2."""
        unit = spaces.Box(-1.0, 1.0, (1,), np.float32)
        return spaces.Dict(
            {
                "side": spaces.Discrete(len(SIDES)),
                "quantity": unit,
                "price": unit,
                "partner": spaces.Discrete(len(self.agents_id) + 1),
            }
        )

    # --- Partners --------------------------------------------------------------------
    def partners(self, pid: str) -> list[str]:
        """Agent ``pid``'s partner candidates, in the order of its ``partner``
        action and of its partner observation: the other participants in scenario
        order, ``"DSO"``, then ``"none"`` (no preference)."""
        return [NO_PREFERENCE if c is None else c for c in self._candidates[pid]]

    def _partner_distances(self) -> dict[str, np.ndarray]:
        """Each agent's grid distance to its peer candidates and to the DSO, divided
        by the largest of them in the network (``distance_scale``)."""
        if not self.market.participants:  # the network is built by a reset
            self.market.scenario.grid.day = self.days[0]
            self.market.reset()
        km = {
            a: np.array(
                [self.market.distance_km(a, c) for c in self._candidates[a][:-1]]
            )
            for a in self.agents_id
        }
        largest = max((float(d.max()) for d in km.values() if d.size), default=0.0)
        self.distance_scale = largest if largest > 0 else 1.0
        return {a: d / self.distance_scale for a, d in km.items()}

    def _partner_names(self) -> tuple[str, ...]:
        """The names of the partner observation (k counts the peer candidates)."""
        peers = range(1, len(self.agents_id))
        return (
            ("last_preference",)
            + tuple(f"partner_rep_{k}" for k in peers)
            + tuple(f"partner_dist_{k}" for k in peers)
            + ("partner_dist_dso",)
        )

    # --- The environment's contract --------------------------------------------------
    def resolved_config(self) -> dict[str, Any]:
        """The ``env_config`` with the scales this environment resolved: what a run
        records and every later environment of the run (validation, held-out days,
        a restored policy) is built with, so they use the training scales."""
        return self.config | {
            "energy_scale": self.energy_scale,
            "reward_scale": self.reward_scale,
        }

    def contract(self) -> dict[str, Any]:
        """What an observation and an action mean, for the run record."""
        return {
            "observation": list(self.obs_names),
            "action": {
                "components": {
                    "side": {"kind": "categorical", "values": list(SIDES)},
                    "quantity": {
                        "kind": "continuous",
                        "bounds": [-1.0, 1.0],
                        "means": "share (q + 1) / 2 of the eq. 15a-b bound",
                        "no_order_share": NO_ORDER_SHARE,
                    },
                    "price": {
                        "kind": "continuous",
                        "bounds": [-1.0, 1.0],
                        "means": "FiT + (p + 1) / 2 · (utility − FiT)",
                        "feed_in_tariff": self.feed_in_tariff,
                        "utility_price": self.utility_price,
                    },
                    "partner": {
                        "kind": "categorical",
                        "values": "partners[agent]",
                    },
                },
                "policy": "factorised over the components",
            },
            "partners": {a: self.partners(a) for a in self.agents_id},
            "scales": {
                "energy_scale": self.energy_scale,
                "reward_scale": self.reward_scale,
                "distance_scale": self.distance_scale,
            },
        }

    def baseline_policies(self, seed: int = 0) -> dict[str, Callable]:
        """The market's baselines, by name: never trade, and the market's own
        bidding rule."""
        return {"zero": zero_policy(self), "net_position": net_position_policy(self)}

    # --- Episodes --------------------------------------------------------------------
    def reset(self, *, seed: Optional[int] = None, options: Optional[dict] = None):
        """Draw a day (or play ``options["day"]``), rebuild the market for it,
        return the first observations and ``{"day": day}`` per agent."""
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        day = (options or {}).get("day")
        if day is None:
            day = self.days[int(self.rng.integers(len(self.days)))]
        elif day not in self.days:
            raise ValueError(f"day {day} is not one of the environment's days")
        self.market.scenario.grid.day = day
        self.market.reset()
        self.last_record = None
        self._clear_memory()
        infos = {a: {"day": day} for a in self.agents_id}
        return self._observe(), infos

    def step(self, action_dict: dict[str, Any]):
        """Play one market step with the agents' orders."""
        intents, chosen = {}, {}
        for pid, action in action_dict.items():
            chosen[pid] = int(np.asarray(action["partner"]).reshape(-1)[0])
            intent = self.decode(pid, action)
            if intent is not None:
                intents[pid] = intent
        record = self.market.step(intents)
        self.last_record = record

        shared, shared_state = _market_infos(record)
        orders = {order.agent_id: order for order in record.orders}
        preference = _preference_kwh(record)
        rewards, infos = {}, {}
        for pid in self.agents_id:
            o = record.participants[pid]
            bill = o.profit - self.utility_price * o.deferred_demand_kwh
            rewards[pid] = bill / self.reward_scale
            order = orders.get(pid)
            battery = self.market.participants[pid].battery
            infos[pid] = {
                "profit": float(o.profit),
                "bill": float(bill),
                "bought_kwh": float(o.bought_kwh),
                "sold_kwh": float(o.sold_kwh),
                "preference_kwh": float(preference.get(pid, 0.0)),
                "deferred_demand_kwh": float(o.deferred_demand_kwh),
                "deferred_supply_kwh": float(o.deferred_supply_kwh),
                "state": {
                    "order_kwh": _order_kwh(order),
                    "order_price": float(order.price) if order else float("nan"),
                    "side": _side(order),
                    "partner": _partner(order),
                    "partner_index": (float(chosen[pid]) if order else float("nan")),
                    "partner_mutual": _mutual(order, orders),
                    "soc": float(battery.soc) if battery else float("nan"),
                    "reputation": float(self.market.participants[pid].reputation),
                },
                "shared": shared,
                "shared_state": shared_state,
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
            "preference": {
                pid: preference.get(pid, 0.0) / self.energy_scale
                for pid in self.agents_id
            },
        }
        done = self.market.done
        terminateds = {a: done for a in self.agents_id} | {"__all__": done}
        truncateds = {a: False for a in self.agents_id} | {"__all__": False}
        return self._observe(), rewards, terminateds, truncateds, infos

    # --- Actions ---------------------------------------------------------------------
    def decode(self, pid: str, action: dict) -> Optional[OrderIntent]:
        """The order an action means for the step about to be played (``None``: no
        order; see the module docstring). The partner is passed on as chosen."""
        side = int(np.asarray(action["side"]).reshape(-1)[0])
        q = float(np.clip(np.asarray(action["quantity"]).reshape(-1)[0], -1.0, 1.0))
        p = float(np.clip(np.asarray(action["price"]).reshape(-1)[0], -1.0, 1.0))
        partner = int(np.asarray(action["partner"]).reshape(-1)[0])
        if side not in (0, 1) or not 0 <= partner < len(self._candidates[pid]):
            raise ValueError(f"{pid}: action {action} is outside its space")
        share = (q + 1.0) / 2.0
        if share < NO_ORDER_SHARE:
            return None
        share = (share - NO_ORDER_SHARE) / (1.0 - NO_ORDER_SHARE)
        is_buy = SIDES[side] == "buy"
        participant = self.market.participants[pid]
        step = self.market.current_step
        most = (
            participant.max_buy_kwh(step) if is_buy else participant.max_sell_kwh(step)
        )
        quantity = share * most
        if quantity <= _MIN_ORDER_KWH:
            return None
        spread = self.utility_price - self.feed_in_tariff
        price = self.feed_in_tariff + (p + 1.0) / 2.0 * spread
        return OrderIntent(
            pid, is_buy, float(price), float(quantity), self._candidates[pid][partner]
        )

    def encode(
        self,
        pid: str,
        side: str,
        share: float,
        price_share: float,
        partner: Optional[str] = None,
    ) -> dict[str, Any]:
        """The action that ``decode`` reads as an order of ``share`` (0 to 1) of the
        eq. 15 bound on ``side`` at ``price_share`` (0 FiT, 1 utility) naming
        ``partner`` (a participant, ``"DSO"`` or ``None`` / ``"none"``); share 0 is
        no order. For baselines and tests."""
        if share <= 0:
            q = -1.0
        else:
            q = 2.0 * (NO_ORDER_SHARE + (1.0 - NO_ORDER_SHARE) * min(share, 1.0)) - 1.0
        names = self.partners(pid)
        return {
            "side": SIDES.index(side),
            "quantity": np.array([q], dtype=np.float32),
            "price": np.array([2.0 * price_share - 1.0], dtype=np.float32),
            "partner": names.index(partner or NO_PREFERENCE),
        }

    # --- Observations ----------------------------------------------------------------
    def _clear_memory(self) -> None:
        """Forget the last step: what the observation reports of it is 0 again."""
        self._memory = {
            "p2p": 0.0,
            "dso": 0.0,
            "balance": 0.0,
            "reward": {a: 0.0 for a in self.agents_id},
            "traded": {a: 0.0 for a in self.agents_id},
            "preference": {a: 0.0 for a in self.agents_id},
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
        reputation = {pid: q.reputation for pid, q in m.participants.items()}
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
                self._memory["preference"][pid],
                *(reputation[c] for c in self._candidates[pid][:-2]),
                *self._distances[pid],
            )
            out[pid] = np.clip(
                np.array(values, dtype=np.float32), -_OBS_LIMIT, _OBS_LIMIT
            )
        return out


# --------------------------------------------------------------------------------------
# What a step reports (the infos)
# --------------------------------------------------------------------------------------
def _order_kwh(order: Optional[Order]) -> float:
    """The order's quantity, + selling and − buying (0 without an order)."""
    if order is None:
        return 0.0
    return -float(order.quantity) if order.is_buy else float(order.quantity)


def _side(order: Optional[Order]) -> str:
    if order is None:
        return "none"
    return "buy" if order.is_buy else "sell"


def _partner(order: Optional[Order]) -> str:
    if order is None or order.partner_id is None:
        return NO_PREFERENCE
    return order.partner_id


def _mutual(order: Optional[Order], orders: dict[str, Order]) -> float:
    """1 if the peer the order names named its owner back on the other side (the
    condition of stage 1 besides the prices), 0 if not, NaN without a peer named."""
    if order is None or order.partner_id in (None, DSO_ID):
        return float("nan")
    other = orders.get(order.partner_id)
    return float(
        other is not None
        and other.partner_id == order.agent_id
        and other.is_buy != order.is_buy
    )


def _preference_kwh(record: StepRecord) -> dict[str, float]:
    """Energy each participant traded in stage 1, bought and sold."""
    out: dict[str, float] = {}
    for t in record.trades:
        if t.stage == 1:
            out[t.buyer_id] = out.get(t.buyer_id, 0.0) + t.quantity
            out[t.seller_id] = out.get(t.seller_id, 0.0) + t.quantity
    return out


def _number(value: Optional[float]) -> float:
    return float("nan") if value is None else float(value)


def _override(setup: Any, values: Optional[dict], name: str) -> None:
    """Replace fields of a scenario part (``env_config["grid"]`` or ``["dso"]``)."""
    known = {f.name for f in fields(setup)}
    for key, value in (values or {}).items():
        if key not in known:
            raise ValueError(
                f"env_config[{name!r}]: {setup.__class__.__name__} has no {key!r}"
            )
        setattr(setup, key, value)


def _market_infos(record: StepRecord) -> tuple[dict, dict]:
    """The step's market and grid amounts and states (see the module)."""
    grid = record.grid
    exchange = grid.external_grid_kwh if grid.converged else None
    exchange = exchange or 0.0
    shared = {
        "p2p_kwh": float(record.p2p_kwh),
        "preference_kwh": float(sum(t.quantity for t in record.trades if t.stage == 1)),
        "sold_to_dso_kwh": float(record.dso.bought_kwh),
        "bought_from_dso_kwh": float(record.dso.sold_kwh),
        "trade_losses_kwh": float(record.losses_kwh),
        "fees": float(record.fees),
        "grid_import_kwh": float(max(exchange, 0.0)),
        "grid_export_kwh": float(max(-exchange, 0.0)),
        "grid_losses_kwh": float(grid.losses_kwh or 0.0) if grid.converged else 0.0,
        "grid_violations": float(len(grid.violations)) if grid.converged else 0.0,
        "not_converged": 0.0 if grid.converged else 1.0,
    }
    state = {
        "clearing_price": float(record.clearing_price),
        "min_voltage_pu": _number(grid.min_voltage_pu),
        "max_voltage_pu": _number(grid.max_voltage_pu),
        "max_line_loading_percent": _number(grid.max_line_loading_percent),
        "fee_max_line_loading_percent": _number(
            (record.signal or grid).max_line_loading_percent
        ),
    }
    return shared, state


# --------------------------------------------------------------------------------------
# Baseline policies: functions of the observation dict
# --------------------------------------------------------------------------------------
def zero_policy(env: MarketEnv) -> Callable[[dict[str, np.ndarray]], dict]:
    """No orders: every agent's quantity share is 0 (below the no-order
    threshold)."""
    agents = list(env.agents_id)
    return lambda obs: {a: env.encode(a, "sell", 0.0, 0.5) for a in agents}


def net_position_policy(
    env: MarketEnv, margin: float = 0.3, battery_first: bool = True
) -> Callable[[dict[str, np.ndarray]], dict]:
    """The market's own bidding rule (``core/market/bidding.py``) read from the
    observation: a surplus is offered at ``FiT + margin · spread``, a deficit asked
    for at ``utility − margin · spread``, without the rule's jitter and without a
    partner preference.

    With ``battery_first`` (the rule's) the battery takes what it can first, so
    the order is ``net − min(net, chargeable)`` when selling and
    ``−net − min(−net, dischargeable)`` when buying. Without it the agent offers
    its whole surplus or asks for its whole deficit.
    """
    agents = list(env.agents_id)
    index = {name: i for i, name in enumerate(OBS_NAMES)}

    def policy(obs: dict[str, np.ndarray]) -> dict[str, Any]:
        actions = {}
        for pid in agents:
            o = obs[pid]
            net = float(o[index["net"]])
            chargeable = float(o[index["chargeable"]])
            dischargeable = float(o[index["dischargeable"]])
            side, share, price = "sell", 0.0, margin
            if net > _MIN_ORDER_KWH:
                kept = min(net, chargeable) if battery_first else 0.0
                share = (net - kept) / (net + dischargeable)
            elif net < -_MIN_ORDER_KWH:
                kept = min(-net, dischargeable) if battery_first else 0.0
                side, price = "buy", 1.0 - margin
                share = (-net - kept) / (-net + chargeable)
            if share <= _MIN_ORDER_KWH:
                share = 0.0  # nothing left to trade: no order
            actions[pid] = env.encode(pid, side, share, price)
        return actions

    return policy
