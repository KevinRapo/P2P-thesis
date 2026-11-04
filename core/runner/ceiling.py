"""The money ceiling: the most the participants could make on a test period.

Money between peers cancels inside the community (what one pays, another receives),
so the community's money depends only on what it buys from and sells to the DSO.
Generation and demand are fixed; what is left to choose is netting (one participant's
surplus covering another's deficit) and when each battery charges and discharges. A
planner who sees the whole period in advance chooses both with a linear program, per
step t and battery b:

    max   Σ_t  p_FiT,t · e_t − p_util,t · g_t
    s.t.  g_t − e_t + Σ_b (d_b,t − c_b,t) = −Σ_i (G_i,t − D_i,t)     energy balance
          E_b,t = E_b,t−1 + η_c · c_b,t − d_b,t / η_d                [P1] eq. 16
          E_min ≤ E_b,t ≤ E_max,  0 ≤ c_b,t, d_b,t ≤ P_b · Δt       [P1] eq. 15c-d
          g_t, e_t ≥ 0;  E_b,T ≥ E_b,start with ``keep_end``

with g the import, e the export, c and d the energy a battery draws from and gives to
the bus, E its stored energy. Every outcome the market can produce is one feasible
point of it, so no policy makes more money, as long as the fees count as nothing (the
zone bonus is a negative fee) and the peer charge is 0 (with a charge, netting through
peers costs money and the bound is looser). It ignores the grid's limits and losses.

    optimise(...)       the program for one or more sites (groups that net together)
    ceiling_days(...)   one run's test periods from its held-out tables: the ceiling's
                        money and stored change per test day, as a policy ``ceiling``
    alone_days(...)     the non-P2P reference of the same periods: each participant's
                        own optimum with the retailer (Zhou et al. 2018), per day

``notebooks/market/market_ceiling.ipynb`` shows it on the current test horizon.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.optimize import linprog

from core.runner.indicators import CEILING as POLICY


@dataclass(frozen=True)
class Store:
    """One battery as the program sees it ([P1] eq. 16, with ``BatterySetup``'s
    fields). ``site``: the group it nets with (``optimise``)."""

    capacity_kwh: float
    min_soc: float
    max_soc: float
    charge_efficiency: float
    discharge_efficiency: float
    start_kwh: float
    max_power_kw: Optional[float] = None
    site: int = 0

    @classmethod
    def from_setup(
        cls, setup: Any, start_kwh: Optional[float] = None, site: int = 0
    ) -> "Store":
        """From a ``BatterySetup`` or its dict; the start defaults to its initial
        state of charge."""
        get = setup.get if isinstance(setup, Mapping) else lambda k: getattr(setup, k)
        capacity = float(get("capacity_kwh"))
        start = capacity * float(get("initial_soc")) if start_kwh is None else start_kwh

        return cls(
            capacity_kwh=capacity,
            min_soc=float(get("min_soc")),
            max_soc=float(get("max_soc")),
            charge_efficiency=float(get("charge_efficiency")),
            discharge_efficiency=float(get("discharge_efficiency")),
            start_kwh=float(start),
            max_power_kw=get("max_power_kw"),
            site=site,
        )


@dataclass(frozen=True)
class Plan:
    """The program's answer.

    Attributes:
        value: The money over the period.
        steps: Per step: ``import``, ``export`` (summed over the sites), ``money``,
            and the batteries' ``charge``, ``discharge`` and ``stored`` summed.
        charge, discharge, stored: Per step, a column per battery.
    """

    value: float
    steps: pd.DataFrame
    charge: pd.DataFrame
    discharge: pd.DataFrame
    stored: pd.DataFrame


def optimise(
    net_kwh: np.ndarray,
    feed_in: np.ndarray,
    utility: np.ndarray,
    stores: Sequence[Store] = (),
    step_hours: float = 1.0,
    keep_end: bool = True,
) -> Plan:
    """The best money a planner with perfect foresight could make.

    Args:
        net_kwh: G − D per step, summed over a site's participants: shape (T,) for
            one site, (S, T) for S sites that each net only internally.
        feed_in: The feed-in tariff per step.
        utility: The utility price per step.
        stores: The batteries, each on its ``site``.
        step_hours: Hours per step, for the power limits.
        keep_end: Every battery ends at least as full as it started.
    """
    net = np.atleast_2d(np.asarray(net_kwh, dtype=float))
    fit, util = np.asarray(feed_in, float), np.asarray(utility, float)
    sites, T = net.shape
    B = len(stores)

    # Variables in blocks: import and export per site, then per battery its charge,
    # discharge and stored energy. ``index`` maps a block to the variables' numbers.
    sizes = [sites * T, sites * T, B * T, B * T, B * T]
    starts = np.cumsum([0, *sizes])
    n = int(starts[-1])

    def index(block: int, rows: int) -> np.ndarray:
        return np.arange(starts[block], starts[block + 1]).reshape(rows, T)

    buy, sell = index(0, sites), index(1, sites)
    charge, discharge, stored = index(2, B), index(3, B), index(4, B)

    cost = np.zeros(n)  # linprog minimises: import cost minus export income
    cost[buy] = util
    cost[sell] = -fit

    lower, upper = np.zeros(n), np.full(n, np.inf)

    for b, s in enumerate(stores):
        if s.max_power_kw is not None:
            upper[charge[b]] = upper[discharge[b]] = s.max_power_kw * step_hours
        lower[stored[b]] = s.min_soc * s.capacity_kwh
        upper[stored[b]] = s.max_soc * s.capacity_kwh

    rows, cols, vals = [], [], []
    rhs = np.zeros(sites * T + B * T)

    def put(row: int, col: Any, value: float) -> None:
        rows.append(row)
        cols.append(int(col))
        vals.append(value)

    # Energy balance per site and step: g − e + Σ (d − c) = −(G − D).
    for k in range(sites):
        on_site = [b for b, s in enumerate(stores) if s.site == k]
        for t in range(T):
            row = k * T + t
            put(row, buy[k, t], 1.0)
            put(row, sell[k, t], -1.0)
            for b in on_site:
                put(row, discharge[b, t], 1.0)
                put(row, charge[b, t], -1.0)
            rhs[row] = -net[k, t]

    # Stored energy, eq. 16: E_t − E_{t−1} − η_c · c_t + d_t / η_d = 0.
    for b, s in enumerate(stores):
        for t in range(T):
            row = sites * T + b * T + t
            put(row, stored[b, t], 1.0)
            put(row, charge[b, t], -s.charge_efficiency)
            put(row, discharge[b, t], 1.0 / s.discharge_efficiency)
            if t:
                put(row, stored[b, t - 1], -1.0)
            else:
                rhs[row] = s.start_kwh

    equal = sp.csr_matrix((vals, (rows, cols)), shape=(len(rhs), n))
    bound_rows, bound_rhs = None, None

    if keep_end and B:  # −E_T ≤ −E_start
        ends = [stored[b, T - 1] for b in range(B)]
        bound_rows = sp.csr_matrix(
            (-np.ones(B), (np.arange(B), ends)), shape=(B, n)
        )
        bound_rhs = -np.array([s.start_kwh for s in stores])

    found = linprog(
        cost,
        A_ub=bound_rows,
        b_ub=bound_rhs,
        A_eq=equal,
        b_eq=rhs,
        bounds=np.column_stack([lower, upper]),
        method="highs",
    )

    if found.status != 0:
        raise ValueError(f"The ceiling has no solution: {found.message}")

    x = found.x
    names = [f"battery {b}" for b in range(B)]
    per = {
        name: pd.DataFrame(x[block].T if B else np.zeros((T, 0)), columns=names)
        for name, block in (
            ("charge", charge),
            ("discharge", discharge),
            ("stored", stored),
        )
    }
    imported, exported = x[buy].sum(axis=0), x[sell].sum(axis=0)
    steps = pd.DataFrame(
        {
            "import": imported,
            "export": exported,
            "money": fit * exported - util * imported,
            "charge": per["charge"].sum(axis=1),
            "discharge": per["discharge"].sum(axis=1),
            "stored": per["stored"].sum(axis=1),
        }
    )

    return Plan(value=-float(found.fun), steps=steps, **per)


def _periods(
    agent_steps: Optional[pd.DataFrame],
    steps: Optional[pd.DataFrame],
    scenario: Optional[Mapping[str, Any]],
):
    """Each test period of a run's held-out tables, as the evaluation played it: its
    days in order, the batteries carried from one to the next. Yields ``(days, part,
    prices, stores)``: the period's agent steps in order (``_d`` the day's place),
    the tariffs on the same steps, and every battery as a ``Store`` starting where
    the evaluation's did (its energy after the first step, less what that step
    changed), by owner. Nothing without the tables, the scenario or a period."""
    need = {"generation_kwh", "demand_kwh", "soc", "stored_change_kwh", "period"}

    if agent_steps is None or steps is None or not scenario:
        return

    if not need <= set(agent_steps) or "period" not in steps:
        return

    setups = {
        p["id"]: p["battery"]
        for p in scenario.get("participants", [])
        if p.get("battery")
    }
    policy = agent_steps.policy.iloc[0]  # any policy: they all start the same
    mine = agent_steps[agent_steps.policy == policy]
    tariffs = steps[steps.policy == policy]

    for _, part in mine.groupby("period", sort=False):
        days = list(dict.fromkeys(part.day))
        order = {d: i for i, d in enumerate(days)}
        part = part.assign(_d=part.day.map(order)).sort_values(["_d", "step"])
        at = pd.MultiIndex.from_frame(part[["_d", "step"]].drop_duplicates())
        prices = tariffs[tariffs.day.isin(days)]
        prices = prices.assign(_d=prices.day.map(order)).set_index(["_d", "step"])
        prices = prices[["feed_in_tariff", "utility_price"]].reindex(at)
        first = part[(part._d == 0) & (part.step == part.step.min())]
        first = first.set_index("agent")
        stores = {
            a: Store.from_setup(
                s,
                start_kwh=float(
                    first.soc[a] * s["capacity_kwh"] - first.stored_change_kwh[a]
                ),
            )
            for a, s in setups.items()
            if a in first.index
        }
        yield days, part, prices, stores


def _by_day(plan: Plan, days: list, at: pd.Index, start: float) -> pd.DataFrame:
    """A plan's money and stored change per day of its period."""
    day = np.array([days[d] for d in at.get_level_values(0)])
    stored = plan.steps.stored.groupby(day, sort=False).last()
    money = plan.steps.money.groupby(day, sort=False).sum().reindex(stored.index)

    return pd.DataFrame(
        {
            "day": stored.index,
            "money": money.to_numpy(),
            "stored_change_kwh": (stored - stored.shift(fill_value=start)).to_numpy(),
        }
    )


def ceiling_days(
    agent_steps: Optional[pd.DataFrame],
    steps: Optional[pd.DataFrame],
    scenario: Optional[Mapping[str, Any]],
) -> Optional[pd.DataFrame]:
    """The ceiling of every test period of a run, from its held-out tables: a row per
    test day (policy ``ceiling``) with ``team_money`` and ``stored_change_kwh``.
    One planner for the whole community, its batteries ending at least as full as
    they started. ``None`` without the tables, the scenario or a period.

    Args:
        agent_steps: ``heldout_agent_steps``: generation, demand, the batteries'
            state of charge and change per participant and step.
        steps: ``heldout_steps``: the tariffs per step.
        scenario: The run's scenario (``scenario.json``), for the batteries.
    """
    hours = float((scenario or {}).get("grid", {}).get("step_hours", 1.0))
    found = []

    for days, part, prices, stores in _periods(agent_steps, steps, scenario):
        net = (part.generation_kwh - part.demand_kwh).groupby([part._d, part.step]).sum()
        plan = optimise(
            net.to_numpy(),
            prices.feed_in_tariff.to_numpy(),
            prices.utility_price.to_numpy(),
            list(stores.values()),
            hours,
        )
        start = sum(s.start_kwh for s in stores.values())
        day = _by_day(plan, days, net.index, start)
        found.append(day.rename(columns={"money": "team_money"}).assign(policy=POLICY))

    if not found:
        return None

    return pd.concat(found, ignore_index=True).set_index(["policy", "day"])


def alone_days(
    agent_steps: Optional[pd.DataFrame],
    steps: Optional[pd.DataFrame],
    scenario: Optional[Mapping[str, Any]],
) -> Optional[pd.DataFrame]:
    """The non-P2P reference of Zhou et al. (2018, §4.1): every participant on its
    own with the retailer, its own battery timed with perfect foresight of its own
    profiles and the tariffs over the test period, ending at least as full as it
    started (their A15), no netting with anyone. A participant without a battery has
    nothing to choose: its surplus at the feed-in tariff, its deficit at the utility
    price. A row per day and participant: ``period``, ``bill``, ``stored_change_kwh``.

    Args:
        agent_steps: ``heldout_agent_steps``, as for ``ceiling_days``.
        steps: ``heldout_steps``, the tariffs per step.
        scenario: The run's scenario, for the batteries.
    """
    hours = float((scenario or {}).get("grid", {}).get("step_hours", 1.0))
    found = []

    for days, part, prices, stores in _periods(agent_steps, steps, scenario):
        period = part.period.iloc[0]

        for agent, own in part.groupby("agent", sort=False):
            net = (own.generation_kwh - own.demand_kwh).to_numpy()
            at = pd.MultiIndex.from_frame(own[["_d", "step"]])
            store = [stores[agent]] if agent in stores else []
            plan = optimise(
                net,
                prices.feed_in_tariff.reindex(at).to_numpy(),
                prices.utility_price.reindex(at).to_numpy(),
                store,
                hours,
            )
            start = store[0].start_kwh if store else 0.0
            day = _by_day(plan, days, at, start)
            found.append(
                day.rename(columns={"money": "bill"}).assign(agent=agent, period=period)
            )

    return pd.concat(found, ignore_index=True) if found else None


def day_references(
    agent_steps: Optional[pd.DataFrame],
    steps: Optional[pd.DataFrame],
    scenario: Optional[Mapping[str, Any]],
) -> tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """The ceiling and the non-P2P reference with every test day its own horizon, as
    Zhou et al. (2018) evaluate one day: each battery starts the day at the scenario's
    initial charge and ends it at least as full. Returns ``(ceiling, alone)``: the
    ceiling's ``team_money`` per day (indexed like ``ceiling_days``), and each
    participant's own optimum per day (``day``, ``agent``, ``bill``). The policies'
    batteries carry over from day to day, so a day's value for them also holds energy
    moved between days; the period references (``ceiling_days``, ``alone_days``) do
    not have that limit. ``(None, None)`` without the tables or the scenario.

    Args:
        agent_steps: ``heldout_agent_steps``: generation and demand per step.
        steps: ``heldout_steps``: the tariffs per step.
        scenario: The run's scenario (``scenario.json``), for the batteries.
    """
    need = {"generation_kwh", "demand_kwh"}

    if agent_steps is None or steps is None or not scenario:
        return None, None

    if not need <= set(agent_steps) or "feed_in_tariff" not in steps:
        return None, None

    setups = {
        p["id"]: p["battery"]
        for p in scenario.get("participants", [])
        if p.get("battery")
    }
    hours = float(scenario.get("grid", {}).get("step_hours", 1.0))
    policy = agent_steps.policy.iloc[0]  # profiles and tariffs: the same for all
    mine = agent_steps[agent_steps.policy == policy]
    tariffs = steps[steps.policy == policy].set_index(["day", "step"])
    tops, alone = [], []

    for day, part in mine.groupby("day", sort=False):
        part = part.sort_values("step")
        at = pd.MultiIndex.from_arrays([part.day, part.step]).unique()
        fit = tariffs.feed_in_tariff.reindex(at).to_numpy()
        util = tariffs.utility_price.reindex(at).to_numpy()
        net = (part.generation_kwh - part.demand_kwh).groupby(part.step).sum()
        stores = {a: Store.from_setup(s) for a, s in setups.items()}
        top = optimise(net.to_numpy(), fit, util, list(stores.values()), hours)
        tops.append({"policy": POLICY, "day": day, "team_money": top.value})

        for agent, own in part.groupby("agent", sort=False):
            mine_net = (own.generation_kwh - own.demand_kwh).to_numpy()
            store = [stores[agent]] if agent in stores else []
            value = optimise(mine_net, fit, util, store, hours).value
            alone.append({"day": day, "agent": agent, "bill": value})

    if not tops:
        return None, None

    return pd.DataFrame(tops).set_index(["policy", "day"]), pd.DataFrame(alone)
