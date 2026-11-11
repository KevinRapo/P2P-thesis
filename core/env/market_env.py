"""MarketEnv: the local energy market as a multi-agent RLlib environment.

One agent per scenario participant. An episode is one market day, or a window of
``episode_days`` days (below); one step is one market step (24 hourly or 96
quarter-hourly a day). The environment only translates: it
turns the agents' actions into ``OrderIntent`` s, lets ``LocalEnergyMarket`` play
the step, and turns the step's record back into observations and rewards. No
market rule lives here (``core/market/`` stays the one place for those).

Observation (``obs_names``, one vector per agent, values clipped to [-10, 10]),
computed for the step about to be played: with the default ``observation = "paper"``
the paper's 42 signals ([P1] Table 2, computed in ``core/market/signals.py``) in its
three groups, with ``"pruned"`` the 22 of ``signals.PRUNED_OBS``; then the other
agents' reputations, which [P1] adds when partner preference is on:

    market (16, public)   ``MARKET_OBS``: hour_sin, hour_cos (sin and cos of the day
                          gone by, in place of the signals step and time of day),
                          then the market signals of the last step
    agent (16, private)   ``AGENT_OBS``: the agent's own profile, outcomes so far,
                          reputation and battery
    KPIs (10, shared)     ``KPI_OBS``: the implicit-cooperation KPIs over the day so
                          far
    partner_rep_k         candidate k's reputation (eq. 12), for the N − 1 other
                          participants, in the agent's candidate order (below)

Scaling (``_obs_scales``), with E = ``energy_scale``, N agents, T steps a day: prices
as (p − FiT) / (utility − FiT), price differences / (utility − FiT), FiT the day's
lowest and utility the day's highest tariff (the same scale at every hour, so the
time-of-use price itself is seen: ``dso_buy_price``, ``dso_sell_price``); one step's
energy / E (agent) or / (E · N) (market); energy over the day / (E · T) (agent) or
/ (E · N · T) (KPIs); profit / ``reward_scale``, welfare / (``reward_scale`` · N ·
T); shares, ratios, reputation and the state of charge as they are. A signal that is
NaN (nothing to measure yet, e.g. before the first step) is 0 in the observation.

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
    price     Box([-1, 1]): p_bid = FiT + (p + 1) / 2 · (utility − FiT), with the
              tariffs of the step being played (time-of-use tariffs change by
              hour): −1 is the feed-in tariff, +1 the utility price (the range the
              DSO makes every trade worth)
    partner   Discrete(N): β, an index into the agent's candidates
              (``partners(agent)``): the N − 1 other participants in scenario
              order, then "no preference". Not the DSO (RP-1h): an order that
              finds no peer clears with the DSO in stage 3 anyway, at the same
              tariff (MP-1e), so naming it would change nothing

What is the paper's and what is an encoding choice made here: the four components
and their kinds (price and quantity continuous, side and partner categorical) are
[P1] eq. 2. The quantity as a share of the eq. 15 bound, the no-order threshold,
the price range and the candidate order are this implementation's encoding. The
chosen partner goes into ``OrderIntent.partner_id`` as it is, "no preference"
included (None): the scenario's rule-based partner choice
(``market.partner_preference``) is never applied to an RL agent's order. Stage 1
of the clearing pairs agents that named each other on opposite sides, bid ≥ ask;
every other order goes to the double auction, and what is left to the DSO in stage
3 (``core/market/clearing.py``, unchanged).

Under RLlib the policy is factorised over the components (one distribution each,
``core/rl``): the partner is not conditioned on the sampled side or price.

An agent missing from the action dict places no order.

Reward, per agent and step: the ``reward`` setting chooses it, by default the scaled
net bill (``core/env/reward.py``).

Scales. ``energy_scale`` E defaults to the largest generation or demand of any
participant in any step of any day in ``days``; ``reward_scale`` defaults to
``p_utility · E`` with the day's highest p_utility, the bill for E kWh bought from
the DSO at its dearest, so a reward of −1 is one such purchase. A run resolves
both once, on its training days, and keeps them (``resolved_config``):
validation, the held-out days and a restored policy use
the training values, so an observation and a reward mean the same everywhere.

Episodes. ``reset`` draws a window of ``episode_days`` consecutive days from
``days`` and rebuilds the market for its first day (changing the day and resetting
is cheap; the first reset of a process loads the SimBench network). Inside a window
each day follows the last with the batteries and reputations as they were at
midnight. Settings (MP-1c, RP-1f; the experiment ``day_end.json`` compares them):

    episode_days      days in a window, default 1
    truncate_episode  False: the window's end sets ``terminateds``, the return ends
                      there and energy left in a battery is worth nothing to the
                      agents. True: it sets ``truncateds``, and the final observation
                      is the start of the next calendar day with the batteries and
                      reputations carried over: the state the return bootstraps
                      from is one the critic trains on
    random_start_soc  each window starts with the batteries at a random charge in
                      their window, so that those states are seen
    terminal_value    the window's last reward adds the change of the stored energy
                      at ``stored_kwh_value`` per kWh
    stored_kwh_value  what a stored kWh is worth (default 0): ``adjusted_bill``, and
                      ``terminal_value``

Forecasts. ``remaining_demand`` and ``remaining_supply`` sum the participant's
demand and generation from the current step to the end of the day. The current step
is known (the agent also observes it as ``demand`` and ``generation``); with
``forecast_error`` e > 0 every later step is forecast as its true value times
(1 + ε), ε drawn uniformly from [−e, e] per participant, step and quantity when a
day starts, so the forecast of a step stays the same all day. The market itself
plays the true profiles: only the observation sees the error.

``options["day"]`` plays that one day, one of ``days``, instead of drawing: the
batteries start at their initial charge, none of the settings above changes the
rewards, and the final observation stays on that day. With ``options["carry"]`` the
batteries and reputations start as the last episode of this environment left them,
which is how the held-out evaluation plays a period; ``options["period"]`` is passed
on to the ``reset`` infos.

Infos, per agent and step, in the layout ``core/rl/policy.py`` reads (amounts
are summed over an episode, states only kept step by step; kWh and the scenario's
money unit):

    profit, bill                   the step's profit (eq. 14) and the net bill of
                                   the reward, before scaling
    fees                           the grid fees it paid (eq. 8), its loss
                                   charge included
    loss_kwh, loss_charge          its share of the step's measured losses and
                                   what it paid for it (0 with eq. 18's
                                   losses, ``dso.losses = "trades"``)
    generation_kwh, demand_kwh     its own generation and demand
    bought_kwh, sold_kwh           traded energy, peers and DSO together
    peer_bought_kwh, peer_sold_kwh of it, with peers
    preference_kwh                 traded in stage 1 (mutual preferences)
    deferred_demand_kwh            demand drawn untraded from the upstream grid
    deferred_supply_kwh            surplus spilled untraded
    charge_kwh, discharge_kwh      energy into and out of the battery
    stored_change_kwh              change of the energy stored in the battery
    adjusted_bill                  bill + stored_change_kwh · ``stored_kwh_value``
    state: order_kwh               the order placed, as the market took it after
                                   validation: + sell, − buy, 0 none
           order_price             its price (NaN without an order)
           side                    "buy", "sell" or "none" (no order)
           partner                 the partner named: a participant or "none"
                                   (also "none" without an order)
           partner_index           the partner component's index (NaN without an
                                   order)
           partner_mutual          1 if the partner named this agent back with an
                                   order on the other side, else 0 (NaN without a
                                   peer named)
           action_side, action_quantity, action_price, action_partner
                                   the action's four parts as the policy gave
                                   them, with or without an order (NaN for an
                                   agent missing from the action dict)
           soc                     battery state of charge after the step, 0 to 1
                                   (NaN without a battery)
           reputation              reputation after the step (eq. 12)
           reward_*                what the reward was made of (``Reward.parts``)
    shared: p2p_kwh                energy traded between participants
            preference_kwh         of it, traded in stage 1
            sold_to_dso_kwh        energy participants sold to the DSO (stage 3)
            bought_from_dso_kwh    energy participants bought from the DSO
            trade_losses_kwh       transmission losses of the trades (eq. 18)
            fees                   grid fees of the trades (eq. 8)
            grid_import_kwh        energy the network drew from the upstream grid
            grid_export_kwh        energy it fed into the upstream grid
            grid_losses_kwh        line and transformer losses of the power flow
            voltage_violations     buses outside their voltage limits
            loading_violations     lines and transformers over their limits
            not_converged          1 if the power flow did not converge
            peer_trades            number of trades between participants
    shared_state: clearing_price   the step's clearing price (the last one kept
                                   when no peers traded)
                  peer_price       the same, NaN when no peers traded
                  feed_in_tariff, utility_price
                  min_voltage_pu, max_voltage_pu, max_line_loading_percent,
                  max_trafo_loading_percent
                  fee_max_line_loading_percent: the highest line loading the
                  fees were charged on (the graph model's with ``grid.method =
                  "graph"``, else the power flow's)
                  mean_line_loading_percent: the mean over the lines (NaN if the
                  flow did not converge)
                  grid_balance_kwh: B_grid before the DSO clears ([P1] eq. 20)
    final: the ten KPIs (``signals.KPIS``) over the day, on its last step
    tables: on a played day only (``options["day"]``), the step's rows:
            trades   one per trade: who, price, energy, stage, distance, losses and
                     each fee (``_trade_rows``)
            grid     one per step: bus_voltage/<bus>, line_loading/<line> and, with
                     ``grid.method = "graph"``, fee_line_loading/<line>; NaN when
                     the flow did not converge (``_grid_row``)

The grid amounts are the AC power flow's (the whole network, background
included), whatever ``grid.method``; a flow that did not converge counts 0 for
them.

Baselines map an observation dict to an action dict: ``net_position_policy``, the
market's bidding rule, is the one ``baseline_policies`` gives the RL layer's
evaluation; ``zero_policy`` (no orders) stays for tests.

``env_config`` keys (JSON-serialisable, so RLlib can pass it to its workers):

    scenario      path to a scenario JSON (required)
    days          days ``"YYYY-MM-DD"`` to draw from at each reset (default: the
                  scenario's day; ``reset(options={"day": ...})`` plays one of them)
    energy_scale  E in kWh (default: computed from ``days``)
    reward_scale  default ``p_utility · E``
    reward        which reward agents learn from: ``"bill"`` (default) or ``"salazar"``
    grid_capacity_kwh  the grid capacity C of the ``"salazar"`` reward
    observation   which signals agents see: ``"paper"`` (default) or ``"pruned"``
    tariff_range  [lowest p_FiT, highest p_utility] scaling prices (default: from
                  ``days``)
    forecast_error  the largest relative error of the forecasts behind
                  ``remaining_demand`` and ``remaining_supply`` (default 0: the true
                  future; [P2] Table 7 gives 0.3). See Forecasts
    seed          seed of the day draw for the first reset
    episode_days, truncate_episode, random_start_soc, terminal_value,
    stored_kwh_value: see Episodes
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
from gymnasium import spaces
from ray.rllib.env.multi_agent_env import MultiAgentEnv

from core.config import store
from core.env.reward import build_reward, net_bill, side_kwh
from core.env_defaults import ENV_CONFIG_KEYS, SCALE_KEYS as SCALE_KEYS
from core.grid.contract import GridAssessment
from core.market import signals
from core.market.lem import LocalEnergyMarket, OrderIntent, StepRecord
from core.market.order import Order

# --------------------------------------------------------------------------------------
# What the agents see and do
# --------------------------------------------------------------------------------------
# The observation sets to choose from (``env_config["observation"]``). **Adding a
# set**: a tuple of signal names (those of ``core/market/signals.py``, with
# hour_sin and hour_cos for the time of day) under a new name in ``OBSERVATIONS``,
# and the name in ``OBSERVATION_NAMES`` of ``core/env_defaults.py``. **Adding a
# signal**: a function in ``signals.py``, registered in its group's dict
# (``MARKET_SIGNALS``, ``AGENT_SIGNALS``, ``KPIS``), and a scale in ``_obs_scales``
# unless it is already about 0 to 1. ``test_every_observation_set_names_known_signals``
# checks every set.
#
# The market signals with the step and time of day as one sin and cos pair.
MARKET_OBS: tuple[str, ...] = ("hour_sin", "hour_cos") + tuple(
    name for name in signals.MARKET_SIGNALS if name not in ("step", "time_of_day")
)
AGENT_OBS: tuple[str, ...] = tuple(signals.AGENT_SIGNALS)
KPI_OBS: tuple[str, ...] = tuple(signals.KPIS)
OBS_NAMES: tuple[str, ...] = MARKET_OBS + AGENT_OBS + KPI_OBS
OBSERVATIONS: dict[str, tuple[str, ...]] = {
    "paper": OBS_NAMES,
    "pruned": signals.PRUNED_OBS,
}
ACTION_COMPONENTS = ("side", "quantity", "price", "partner")
SIDES = ("sell", "buy")  # α: index 0 sells, 1 buys ([P1] eq. 2)
NO_PREFERENCE = "none"  # the last partner candidate: no partner named
NO_ORDER_SHARE = 0.05  # quantity share below this places no order
_OBS_LIMIT = 10.0
_MIN_ORDER_KWH = 1e-9


# --------------------------------------------------------------------------------------
# The environment
# --------------------------------------------------------------------------------------
class MarketEnv(MultiAgentEnv):
    """The local energy market, one agent per participant (see the module docstring).

    Args:
        env_config: ``scenario`` (path, required), ``days`` and ``seed``, plus the
            scaling and episode settings described above. Accepted keys are defined
            in ``core.env_defaults``; grid and DSO settings belong to the scenario.
    """

    def __init__(self, env_config: Optional[dict[str, Any]] = None) -> None:
        super().__init__()
        config = env_config or {}

        if "scenario" not in config:
            raise ValueError("env_config needs 'scenario': the path of a scenario JSON")

        unknown = sorted(set(config) - set(ENV_CONFIG_KEYS))

        if unknown:
            raise ValueError(f"unknown env_config setting(s) {unknown}")

        self.config = dict(config)
        scenario = store.load(Path(config["scenario"]))
        self.market = LocalEnergyMarket(scenario)
        self.days: list[str] = list(config.get("days") or [scenario.grid.day])
        self.episode_days: int = int(config.get("episode_days") or 1)
        self.truncate_episode: bool = bool(config.get("truncate_episode"))
        self.random_start_soc: bool = bool(config.get("random_start_soc"))
        self.terminal_value: bool = bool(config.get("terminal_value"))
        self.stored_kwh_value: float = float(config.get("stored_kwh_value") or 0.0)
        self.forecast_error: float = float(config.get("forecast_error") or 0.0)

        if not 0.0 <= self.forecast_error < 1.0:
            raise ValueError("forecast_error must be in [0, 1)")

        # Per participant, the factors (1 + ε) of each step's forecast demand and
        # generation on the day being played; empty without a forecast error.
        self._forecast: dict[str, tuple[np.ndarray, np.ndarray]] = {}

        if self.terminal_value and not self.stored_kwh_value:
            raise ValueError("terminal_value needs a stored_kwh_value")

        self.windows = _windows(self.days, self.episode_days)
        self.window: list[str] = []
        self.window_day = 0
        self.one_day = False
        self.start_kwh: dict[str, float] = {}
        self.agents_id: list[str] = [p.id for p in scenario.participants]
        self.agents = self.possible_agents = list(self.agents_id)
        # The days' lowest p_FiT and highest p_utility: the fixed scale of prices
        # and rewards (the step's own tariffs are the DSO's, ``self.market.dso``).
        self.feed_in_tariff, self.utility_price = config.get(
            "tariff_range"
        ) or self.market.dso.tariff_range(self.days)
        self.energy_scale: float = float(
            config.get("energy_scale") or self._largest_energy()
        )
        self.reward_scale: float = float(
            config.get("reward_scale") or self.utility_price * self.energy_scale
        )
        self.reward_name: str = config.get("reward") or "bill"
        self.reward = build_reward(
            self.reward_name,
            self.market,
            self.reward_scale,
            config.get("grid_capacity_kwh"),
        )
        # DEVIATION RP-1h: β names a peer or nobody, never the DSO (see the module).
        self._candidates = {
            a: [b for b in self.agents_id if b != a] + [None]
            for a in self.agents_id
        }
        observation = config.get("observation") or "paper"

        if observation not in OBSERVATIONS:
            raise ValueError(
                f"unknown observation {observation!r}; "
                f"choose from {sorted(OBSERVATIONS)}"
            )

        self.obs_names: tuple[str, ...] = OBSERVATIONS[observation] + tuple(
            f"partner_rep_{k}" for k in range(1, len(self.agents_id))
        )
        self._signal_names = OBSERVATIONS[observation]
        self._scales = self._obs_scales()
        # The signals the observation reads (``_observe`` computes only these), and
        # whether it reads a KPI
        self._wanted = frozenset(self._scales) | {"time_of_day"}
        self._observes_kpis = bool(self._wanted & set(signals.KPIS))
        obs_box = spaces.Box(
            -_OBS_LIMIT, _OBS_LIMIT, (len(self.obs_names),), np.float32
        )
        self.observation_spaces = {a: obs_box for a in self.agents_id}
        self.action_spaces = {a: self._action_space() for a in self.agents_id}
        self.rng = np.random.default_rng(config.get("seed"))
        self.last_record: Optional[StepRecord] = None

    def _largest_energy(self) -> float:
        """The largest generation or demand (kWh) of any participant in any step
        of any day in ``days``: the default ``energy_scale`` (at least 1e-6). Read
        from the profiles alone (``LocalEnergyMarket.profiles``), without playing or
        resetting the market."""
        largest = 0.0

        for day in self.days:
            for generation, demand in self.market.profiles(day).values():
                largest = max(largest, max(generation), max(demand))

        return max(largest, 1e-6)

    def _action_space(self) -> spaces.Dict: #! Action shape
        """One agent's action: the four components of [P1] eq. 2."""
        unit = spaces.Box(-1.0, 1.0, (1,), np.float32)
        return spaces.Dict(
            {
                "side": spaces.Discrete(len(SIDES)),
                "quantity": unit,
                "price": unit,
                "partner": spaces.Discrete(len(self.agents_id)),
            }
        )

    # --- Partners --------------------------------------------------------------------
    def partners(self, pid: str) -> list[str]:
        """Agent ``pid``'s partner candidates, in the order of its ``partner``
        action and of its partner observation: the other participants in scenario
        order, then ``"none"`` (no preference)."""
        return [NO_PREFERENCE if c is None else c for c in self._candidates[pid]]

    # --- The environment's contract --------------------------------------------------
    def resolved_config(self) -> dict[str, Any]:
        """The ``env_config`` with the scales this environment resolved: what a run
        records and every later environment of the run (validation, held-out days,
        a restored policy) is built with, so they use the training scales."""
        return self.config | {
            "energy_scale": self.energy_scale,
            "reward_scale": self.reward_scale,
            "tariff_range": [self.feed_in_tariff, self.utility_price],
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
                        "means": "FiT + (p + 1) / 2 · (peer ceiling − FiT), the step's",
                        "feed_in_tariff": self.feed_in_tariff,
                        "utility_price": self.utility_price,
                        "prices": {
                            kind: series
                            for kind, series in self.market.dso.prices.items()
                            if kind != "days"
                        },
                    },
                    "partner": {
                        "kind": "categorical",
                        "values": "partners[agent]",
                    },
                },
                "policy": "factorised over the components",
            },
            "partners": {a: self.partners(a) for a in self.agents_id},
            "reward": self.reward_name,
            "scales": {
                "energy_scale": self.energy_scale,
                "reward_scale": self.reward_scale,
            },
        }

    def baseline_policies(self, seed: int = 0) -> dict[str, Callable]:
        """The market's played baseline, by name: its own bidding rule. (The other
        references, ``non_p2p`` and the ceiling, are calculated, not played.)"""
        return {"net_position": net_position_policy(self)}

    # --- Episodes --------------------------------------------------------------------
    def reset(self, *, seed: Optional[int] = None, options: Optional[dict] = None):  #! Episode: reset (one day)
        """Draw a window of days (or play ``options["day"]``, see the module), rebuild
        the market for its first day, return the first observations and ``{"day":
        day}`` per agent (with the ``period`` of ``options``, if any)."""
        options = options or {}

        if seed is not None:
            self.rng = np.random.default_rng(seed)

        day = options.get("day")
        self.one_day = day is not None

        if day is None:
            self.window = self.windows[int(self.rng.integers(len(self.windows)))]
        elif day in self.days:
            self.window = [day]
        else:
            raise ValueError(f"day {day} is not one of the environment's days")

        self.window_day = 0

        if options.get("carry"):
            self._play(self.window[0], self._stored_kwh(), self._reputations())
        elif self.random_start_soc and not self.one_day:
            self._play(self.window[0], self._random_kwh())
        else:
            self._play(self.window[0])

        self.start_kwh = self._stored_kwh()
        self.last_record = None
        info = {"day": self.window[0]}

        if "period" in options:
            info["period"] = options["period"]

        return self._observe(), {a: dict(info) for a in self.agents_id}

    def step(self, action_dict: dict[str, Any]):  #! Environment step: E1-E4
        """Play one market step with the agents' orders."""
        intents, chosen, raw = {}, {}, {}

        for pid, action in action_dict.items():
            chosen[pid] = int(np.asarray(action["partner"]).reshape(-1)[0])
            raw[pid] = _raw_action(action)
            intent = self.decode(pid, action)
            if intent is not None:
                intents[pid] = intent

        stored = self._stored_kwh()
        record = self.market.step(intents)
        self.last_record = record

        shared, shared_state = _market_infos(record)
        orders = {order.agent_id: order for order in record.orders}
        preference = _preference_kwh(record)
        rewards = self.reward.step(record)
        peer_trades = [t for t in record.trades if t.stage < 3]
        done = self.market.done
        final = {"final": dict(signals.kpis_shared(self.market.history))} if done else {}
        tables = _tables(record) if self.one_day else None
        infos = {}

        for pid in self.agents_id:
            o = record.participants[pid]
            peer_bought, peer_sold = side_kwh(peer_trades, pid)
            bill = net_bill(record, pid)
            order = orders.get(pid)
            battery = self.market.participants[pid].battery
            change = float((o.soc_kwh or 0.0) - stored.get(pid, 0.0))
            infos[pid] = {
                "profit": float(o.profit),
                "bill": float(bill),
                "fees": float(o.fees),
                "loss_kwh": float(record.grid.loss_shares_kwh.get(pid, 0.0)),
                "loss_charge": float(o.loss_charge),
                "generation_kwh": float(o.generation_kwh),
                "demand_kwh": float(o.demand_kwh),
                "bought_kwh": float(o.bought_kwh),
                "sold_kwh": float(o.sold_kwh),
                "peer_bought_kwh": float(peer_bought),
                "peer_sold_kwh": float(peer_sold),
                "preference_kwh": float(preference.get(pid, 0.0)),
                "deferred_demand_kwh": float(o.deferred_demand_kwh),
                "deferred_supply_kwh": float(o.deferred_supply_kwh),
                "charge_kwh": float(o.charge_kwh),
                "discharge_kwh": float(o.discharge_kwh),
                "stored_change_kwh": change,
                "adjusted_bill": float(bill + self.stored_kwh_value * change),
                "state": {
                    "order_kwh": _order_kwh(order),
                    "order_price": float(order.price) if order else float("nan"),
                    "side": _side(order),
                    "partner": _partner(order),
                    "partner_index": (float(chosen[pid]) if order else float("nan")),
                    "partner_mutual": _mutual(order, orders),
                    **raw.get(pid, _NO_ACTION),
                    "soc": float(battery.soc) if battery else float("nan"),
                    "reputation": float(self.market.participants[pid].reputation),
                    **self.reward.parts.get(pid, {}),
                },
                "shared": shared,
                "shared_state": shared_state,
                **final,
            }

            if tables:
                infos[pid]["tables"] = tables

        day_over = self.market.done
        done = day_over and self.window_day == len(self.window) - 1
        cut, ended = (done, False) if self.truncate_episode else (False, done)
        terminateds = {a: ended for a in self.agents_id} | {"__all__": ended}
        truncateds = {a: cut for a in self.agents_id} | {"__all__": cut}

        # On the window's last step, pay each battery the energy it gained since reset
        # (a loss counts as negative): stored energy would otherwise be worth nothing
        # to the agents. Never on a played day (``options["day"]``), so evaluation
        # rewards stay the plain bill.
        if done and self.terminal_value and not self.one_day:
            for pid, kwh in self._stored_kwh().items():
                gain = kwh - self.start_kwh[pid]
                rewards[pid] += self.reward.stored_energy(gain, self.stored_kwh_value)

        if day_over and not self.one_day and (not done or self.truncate_episode):
            self._next_day()

        return self._observe(), rewards, terminateds, truncateds, infos

    # --- Days -------------------------------------------------------------------------
    def _play(
        self,
        day: str,
        battery_kwh: Optional[dict] = None,
        reputation: Optional[dict] = None,
    ) -> None:
        """Rebuild the market for ``day`` and draw its forecast errors."""
        self.market.scenario.grid.day = day
        self.market.reset(battery_kwh, reputation)
        e = self.forecast_error
        n = self.market.n_steps
        self._forecast = {
            pid: tuple(1.0 + self.rng.uniform(-e, e, n) for _ in range(2))
            for pid in self.agents_id
        } if e > 0 else {}

    def _forecasts(self, pid: str) -> dict[str, float]:
        """``remaining_demand`` and ``remaining_supply`` as the agent forecasts them
        (see Forecasts): the current step's true value, every later one with its
        error. Empty without a forecast error."""
        if pid not in self._forecast:
            return {}

        p = self.market.participants[pid]
        t = min(self.market.current_step, self.market.n_steps)
        demand_factor, generation_factor = self._forecast[pid]

        def forecast(true: list[float], factor: np.ndarray) -> float:
            now = true[t] if t < len(true) else 0.0
            return float(now + np.dot(true[t + 1 :], factor[t + 1 : len(true)]))

        return {
            "remaining_demand": forecast(p.demand_kwh, demand_factor),
            "remaining_supply": forecast(p.generation_kwh, generation_factor),
        }

    def _next_day(self) -> None:
        """Move on to the window's next day, or after its last one to the next
        calendar day (the first of the window at the end of the profile year), with
        the batteries and reputations as they are."""
        self.window_day += 1

        if self.window_day < len(self.window):
            day = self.window[self.window_day]
        else:
            following = date.fromisoformat(self.window[-1]) + timedelta(days=1)
            same_year = following.year == date.fromisoformat(self.window[0]).year
            day = following.isoformat() if same_year else self.window[0]

        self._play(day, self._stored_kwh(), self._reputations())

    def _stored_kwh(self) -> dict[str, float]:
        """The energy in each participant's battery."""
        people = self.market.participants.items()
        return {pid: p.battery.energy_kwh for pid, p in people if p.battery}

    def _reputations(self) -> dict[str, float]:
        """Each participant's reputation."""
        return {pid: p.reputation for pid, p in self.market.participants.items()}

    def _random_kwh(self) -> dict[str, float]:
        """A random energy for each battery, inside its state-of-charge window."""
        out = {}

        for p in self.market.scenario.participants:
            b = p.battery
            if b is not None:
                soc = self.rng.uniform(b.min_soc, b.max_soc)
                out[p.id] = float(soc * b.capacity_kwh)

        return out

    # --- Actions ---------------------------------------------------------------------
    def decode(self, pid: str, action: dict) -> Optional[OrderIntent]:  #! E1: action -> intent
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

        fit, top = self.market.dso.feed_in_tariff, self.market.dso.peer_ceiling()
        price = fit + (p + 1.0) / 2.0 * (top - fit)

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
        ``partner`` (a participant, or ``None`` / ``"none"``); share 0 is
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
    def _obs_scales(self) -> dict[str, tuple[float, float]]:
        """Each observed signal's (offset, divisor): it enters the observation as
        (value − offset) / divisor (see the module docstring)."""
        fit, spread = self.feed_in_tariff, self.utility_price - self.feed_in_tariff
        e, n, t = self.energy_scale, len(self.agents_id), self.market.n_steps
        price, difference = (fit, spread), (0.0, spread)
        step, step_all = (0.0, e), (0.0, e * n)
        day, day_all = (0.0, e * t), (0.0, e * n * t)
        kinds = {
            "clearing_price": price,
            "dso_buy_price": price,
            "dso_sell_price": price,
            "mean_local_price": price,
            "price_spread": difference,
            "local_price_advantage": difference,
            "bid_ask_spread": difference,
            "price_volatility": difference,
            **dict.fromkeys(
                (
                    "clearing_volume",
                    "grid_balance",
                    "dso_buy_volume",
                    "dso_sell_volume",
                    "dso_total_volume",
                    "p2p_volume",
                    "net_grid_import",
                ),
                step_all,
            ),
            **dict.fromkeys(
                (
                    "generation",
                    "demand",
                    "battery_energy",
                    "available_charge",
                    "available_discharge",
                ),
                step,
            ),
            **dict.fromkeys(
                (
                    "cumulative_demand_satisfied",
                    "cumulative_demand_deferred",
                    "remaining_demand",
                    "cumulative_supply_satisfied",
                    "cumulative_supply_deferred",
                    "remaining_supply",
                    "cumulative_charge",
                    "cumulative_discharge",
                ),
                day,
            ),
            "liquidity": day_all,
            "mean_profit": (0.0, self.reward_scale),
            "social_welfare": (0.0, self.reward_scale * n * t),
        }

        return {name: kinds.get(name, (0.0, 1.0)) for name in self._signal_names}

    def _observe(self) -> dict[str, np.ndarray]:  #! E3: observation
        """Every agent's observation for the step about to be played (see the module
        docstring). After the last step the profile is the last step's and the hour
        is midnight (the episode is over; RLlib wants a final observation)."""
        m = self.market
        wanted = self._wanted
        values = signals.market_signals(m, wanted)
        angle = 2.0 * np.pi * values["time_of_day"]
        values |= {"hour_sin": np.sin(angle), "hour_cos": np.cos(angle)}

        # OPEN E-10: the KPIs over the day so far; the papers give no window.
        if self._observes_kpis:
            values |= signals.kpis_shared(m.history)  # once per state, with the reward

        out = {}

        for pid in self.agents_id:
            mine = values | signals.agent_signals(m, pid, wanted) | self._forecasts(pid)
            scaled = [
                (mine[name] - offset) / divisor
                for name, (offset, divisor) in self._scales.items()
            ]
            peers = [m.participants[c].reputation for c in self._candidates[pid][:-1]]
            # OPEN E-07: a NaN signal (nothing to measure yet) enters as 0, as in
            # MARLEM. For mean_local_price and local_price_advantage 0 is also a real
            # value (a trade at the feed-in tariff, no advantage), so "no peer trade"
            # cannot be told apart from it.
            vector = np.nan_to_num(np.array(scaled + peers, dtype=np.float32), nan=0.0)
            out[pid] = np.clip(vector, -_OBS_LIMIT, _OBS_LIMIT)

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


# What the policy put out, before decoding (RP-7l): with or without an order, so the
# no-order region and what the policy asked for in it can be seen.
_NO_ACTION = dict.fromkeys(
    ("action_side", "action_quantity", "action_price", "action_partner"), float("nan")
)


def _raw_action(action: dict) -> dict[str, float]:
    """The four parts of one agent's action as numbers, as the policy gave them."""
    return {
        f"action_{part}": float(np.asarray(action[part]).reshape(-1)[0])
        for part in ACTION_COMPONENTS
    }


def _partner(order: Optional[Order]) -> str:
    if order is None or order.partner_id is None:
        return NO_PREFERENCE
    return order.partner_id


def _mutual(order: Optional[Order], orders: dict[str, Order]) -> float:
    """1 if the peer the order names named its owner back on the other side (the
    condition of stage 1 besides the prices), 0 if not, NaN without a peer named."""
    if order is None or order.partner_id is None:
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


def _windows(days: list[str], length: int) -> list[list[str]]:
    """Every run of ``length`` consecutive calendar days inside ``days``; the shorter
    runs when there is none (a test profile with a single training day)."""
    known = set(days)
    runs = []

    for first in days:
        run, day = [first], date.fromisoformat(first)

        while len(run) < length:
            day += timedelta(days=1)
            if day.isoformat() not in known:
                break
            run.append(day.isoformat())

        runs.append(run)

    return [run for run in runs if len(run) == length] or runs


def _number(value: Optional[float]) -> float:
    return float("nan") if value is None else float(value)


def _market_infos(record: StepRecord) -> tuple[dict, dict]:
    """The step's market and grid amounts and states (see the module)."""
    grid = record.grid
    exchange = grid.external_grid_kwh if grid.converged else None
    exchange = exchange or 0.0
    limits = [v.code for v in grid.violations] if grid.converged else []
    shared = {
        "p2p_kwh": float(record.p2p_kwh),
        "preference_kwh": float(sum(t.quantity for t in record.trades if t.stage == 1)),
        "sold_to_dso_kwh": float(record.dso.bought_kwh),
        "bought_from_dso_kwh": float(record.dso.sold_kwh),
        "trade_losses_kwh": float(record.losses_kwh),
        "fees": float(record.fees),
        "peer_charge": float(sum(t.fee_parts.peer_charge for t in record.trades)),
        "grid_import_kwh": float(max(exchange, 0.0)),
        "grid_export_kwh": float(max(-exchange, 0.0)),
        "grid_losses_kwh": float(grid.losses_kwh or 0.0) if grid.converged else 0.0,
        "voltage_violations": float(sum(c in ("V_LOW", "V_HIGH") for c in limits)),
        "loading_violations": float(
            sum(c in ("LINE_OVERLOAD", "TRAFO_OVERLOAD") for c in limits)
        ),
        "not_converged": 0.0 if grid.converged else 1.0,
        "peer_trades": float(sum(t.stage < 3 for t in record.trades)),
    }
    state = {
        "clearing_price": float(record.clearing_price),
        "peer_price": float(record.clearing_price if record.p2p_kwh else "nan"),
        "feed_in_tariff": float(record.inputs.feed_in_tariff),
        "utility_price": float(record.inputs.utility_price),
        "min_voltage_pu": _number(grid.min_voltage_pu),
        "max_voltage_pu": _number(grid.max_voltage_pu),
        "max_line_loading_percent": _number(grid.max_line_loading_percent),
        "max_trafo_loading_percent": _number(grid.max_trafo_loading_percent),
        "fee_max_line_loading_percent": _number(
            (record.signal or grid).max_line_loading_percent
        ),
        "mean_line_loading_percent": _mean_loading(grid),
        "grid_balance_kwh": float(record.grid_balance_kwh),
    }

    return shared, state


def _mean_loading(grid: GridAssessment) -> float:
    """The mean loading over the lines, NaN if the flow did not converge."""
    if not grid.converged or not grid.line_loading_percent:
        return float("nan")

    return float(np.mean(list(grid.line_loading_percent.values())))


def _trade_rows(record: StepRecord) -> list[dict[str, Any]]:
    """One row per trade of the step."""
    return [
        {
            "buyer": t.buyer_id,
            "seller": t.seller_id,
            "price": float(t.price),
            "kwh": float(t.quantity),
            "stage": t.stage,
            "distance_km": float(t.distance),
            "transmission_loss_kwh": float(t.transmission_loss),
            "buyer_fee": float(t.buyer_fee),
            "seller_fee": float(t.seller_fee),
            "fee_congestion": float(t.fee_parts.congestion),
            "fee_transmission": float(t.fee_parts.transmission),
            "fee_imbalance": float(t.fee_parts.imbalance),
            "fee_voltage": float(t.fee_parts.voltage),
            "fee_thermal": float(t.fee_parts.thermal),
            "fee_zone": float(t.fee_parts.zone),
            "peer_charge": float(t.fee_parts.peer_charge),
        }
        for t in record.trades
    ]


def _grid_row(record: StepRecord) -> dict[str, float]:
    """The step's voltage per bus and loading per line, and with the graph model the
    loading the fees read per line. A flow that did not converge leaves its columns
    NaN, whatever it reported."""
    grid = record.grid
    row: dict[str, float] = {}

    if grid.converged:
        row |= {f"bus_voltage/{b}": float(v) for b, v in grid.bus_voltage_pu.items()}
        row |= {
            f"line_loading/{line}": float(value)
            for line, value in grid.line_loading_percent.items()
        }

    if record.signal is not None:
        row |= {
            f"fee_line_loading/{line}": float(value)
            for line, value in record.signal.line_loading_percent.items()
        }

    return row


def _tables(record: StepRecord) -> dict[str, list[dict[str, Any]]]:
    """The step's rows of the played day's tables (see the module)."""
    return {"trades": _trade_rows(record), "grid": [_grid_row(record)]}


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
    """The market's own bidding rule (``core/market/agent/rule_based_bid.py``) read
    from the observation: a surplus is offered at ``FiT + margin · spread``, a deficit asked
    for at ``utility − margin · spread``, without the rule's jitter and without a
    partner preference.

    With ``battery_first`` (the rule's) the battery takes what it can first, so
    the order is ``net − min(net, chargeable)`` when selling and
    ``−net − min(−net, dischargeable)`` when buying. Without it the agent offers
    its whole surplus or asks for its whole deficit.
    """
    agents = list(env.agents_id)
    index = {name: i for i, name in enumerate(env.obs_names)}

    def policy(obs: dict[str, np.ndarray]) -> dict[str, Any]:
        actions = {}
        for pid in agents:
            o = obs[pid]
            net = float(o[index["generation"]] - o[index["demand"]])
            chargeable = float(o[index["available_charge"]])
            dischargeable = float(o[index["available_discharge"]])
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
