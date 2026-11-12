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
point of it, so no policy makes more money, as long as the fees count as nothing (no
fee is below 0: the zone bonus is capped at the fees it cancels, MP-4n; and the fees
of the untraded energy, MP-1f, only lower what a policy makes) and the peer charge is 0
(with a charge, netting through peers costs money and the bound is looser). The
program ignores the grid's limits, losses and fees: its value is **energy money**,
before any grid fee and loss charge, and so is the non-P2P reference's
(``energy_bill``). That is what the VTI compares a policy's ``energy_money`` with.

A reference's schedule fixes every bus's injection (the participants' generation and
demand, and what each battery charges and discharges), so it can run through the
market's own power flow, and, for the non-P2P reference, its fees: every
participant's exchange with the retailer is a settlement with the DSO, charged as the
market charges the energy no trade covers (``LocalEnergyMarket.assess_outcomes``). The
ceiling gets the flow and the loss charge but no fees: it nets the whole community,
so who traded with whom, which a fee needs, is undefined.

    optimise(...)       the program for one or more sites (groups that net together)
    references(...)     all the references of a run at once
    ceiling_days(...)   one run's test periods from its held-out tables: the ceiling's
                        energy money, stored change and grid columns per test day, as a
                        policy ``ceiling``
    alone_days(...)     the non-P2P reference of the same periods: each participant's
                        own optimum with the retailer (Zhou et al. 2018), per day, its
                        fees and loss charge
    day_references(...) both with every test day its own horizon, before fees

``notebooks/market/market_ceiling.ipynb`` shows it on the current test horizon.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, NamedTuple, Optional, Sequence

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.optimize import linprog

from core.market import indicators
from core.market.indicators import CEILING as POLICY


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
    max_power_kw: float
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
            max_power_kw=float(get("max_power_kw")),
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

    if not B and np.all(util >= fit):
        return _settled(net, fit, util)

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


def _settled(net: np.ndarray, fit: np.ndarray, util: np.ndarray) -> Plan:
    """``optimise`` without a battery: nothing to choose, so no program. Each site's
    surplus is exported at the feed-in tariff and its deficit imported at the utility
    price, step by step: the program's own optimum whenever the utility price is not
    below the feed-in tariff (otherwise buying to sell would pay, and ``optimise``
    lets the program say so)."""
    exported = np.clip(net, 0.0, None).sum(axis=0)
    imported = np.clip(-net, 0.0, None).sum(axis=0)
    money = fit * exported - util * imported
    none = pd.DataFrame(index=range(net.shape[1]))
    zero = np.zeros(net.shape[1])
    steps = pd.DataFrame(
        {
            "import": imported,
            "export": exported,
            "money": money,
            "charge": zero,
            "discharge": zero,
            "stored": zero,
        }
    )

    return Plan(
        value=float(money.sum()),
        steps=steps,
        charge=none.copy(),
        discharge=none.copy(),
        stored=none.copy(),
    )


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

    setups = _batteries(scenario)
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


def _batteries(scenario: Mapping[str, Any]) -> dict[str, dict]:
    """Each participant's battery as the market played it: the saved setup with its
    capacity and power limit times the scenario's ``storage_scale`` (MP-4i)."""
    factor = float(scenario.get("grid", {}).get("storage_scale", 1.0))
    found = {}

    for p in scenario.get("participants", []):
        if p.get("battery"):
            b = dict(p["battery"])
            b["capacity_kwh"] = float(b["capacity_kwh"]) * factor
            if b.get("max_power_kw") is not None:
                b["max_power_kw"] = float(b["max_power_kw"]) * factor
            found[p["id"]] = b

    return found


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


# --------------------------------------------------------------------------------------
# The power flow on a reference
# --------------------------------------------------------------------------------------
def _market_of(scenario: Optional[Mapping[str, Any]]) -> Any:
    """The market the run was played on, to run its power flow and its fees on a
    reference's schedule: the same network, background, scales, loss rule and DSO.
    None when the scenario does not say enough to build one (a test's partial one)."""
    if not scenario or not scenario.get("participants"):
        return None

    if "code" not in scenario.get("grid", {}):
        return None

    from core.config import store
    from core.market.lem import LocalEnergyMarket

    try:
        return LocalEnergyMarket(store.from_dict(dict(scenario)))
    except (KeyError, TypeError, ValueError):
        return None


def _flows(
    market: Any,
    days: list,
    at: pd.MultiIndex,
    prices: pd.DataFrame,
    part: pd.DataFrame,
    charge: pd.DataFrame,
    discharge: pd.DataFrame,
    fees: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The power flow of a schedule, step by step, as the market runs it (``market``,
    ``LocalEnergyMarket.assess_outcomes``): every participant's injection is what it
    generates and discharges less what it uses and charges, never a trade. With
    ``fees`` its energy exchange is a settlement with the DSO, charged as the market
    charges the energy no trade covers.

    Args:
        market: The run's market (``_market_of``).
        days: The period's days in order; ``at`` holds their index and the step.
        at: The period's steps, ``(day index, step)``.
        prices: The tariffs on ``at``.
        part: The period's agent steps (generation and demand per participant).
        charge, discharge: What each battery draws from and gives to the bus, a column
            per owner, on ``at``; an owner left out has none.
        fees: Charge the settlements.

    Returns:
        ``(steps, people)``: a row per step with the columns of a held-out step table
        (the flow's extremes, the exchange, the losses, the violations, ``fees``,
        ``loss_charge``), and a row per step and participant with its ``fees`` and
        ``loss_charge``.
    """
    from core.market.agent.der import ParticipantOutcome
    from core.market.lem import StepInputs

    def wide(column: str) -> pd.DataFrame:
        table = part.pivot(index=["_d", "step"], columns="agent", values=column)
        return table.reindex(at).fillna(0.0)

    gen, dem = wide("generation_kwh"), wide("demand_kwh")
    steps, people = [], []
    current = None

    for n, (d, step) in enumerate(at):
        if d != current:
            market.scenario.grid.day = days[d]
            market.reset()
            current = d

        fit, util = prices.feed_in_tariff.iloc[n], prices.utility_price.iloc[n]
        outcomes, g_now, d_now = {}, {}, {}

        for pid in market.participants:
            g = float(gen[pid].iloc[n]) if pid in gen else 0.0
            use = float(dem[pid].iloc[n]) if pid in dem else 0.0
            c = float(charge[pid].iloc[n]) if pid in charge else 0.0
            x = float(discharge[pid].iloc[n]) if pid in discharge else 0.0
            g_now[pid], d_now[pid] = g, use
            outcomes[pid] = ParticipantOutcome(
                participant_id=pid,
                generation_kwh=g,
                demand_kwh=use,
                bought_kwh=0.0,
                sold_kwh=0.0,
                charge_kwh=c,
                discharge_kwh=x,
                external_kwh=g - use - c + x,
                soc_kwh=None,
                balance_kwh=g - use,
                fees=0.0,
                profit=0.0,
            )

        inputs = StepInputs(step, g_now, d_now, float(fit), float(util))
        grid, settled, charges = market.assess_outcomes(inputs, outcomes, fees)
        steps.append(_step_row(days[d], step, fit, util, grid, settled, charges, fees))

        for pid in outcomes:
            mine = sum(
                t.buyer_fee if t.buyer_id == pid else t.seller_fee
                for t in settled
                if pid in (t.buyer_id, t.seller_id)
            )
            people.append(
                {"day": days[d], "step": step, "agent": pid,
                 "fees": mine, "loss_charge": charges.get(pid, 0.0)}
            )

    return pd.DataFrame(steps), pd.DataFrame(people)


def _step_row(
    day: str, step: int, fit: float, util: float, grid: Any, settled: Sequence,
    charges: Mapping[str, float], fees: bool,
) -> dict:
    """One step of a reference as a row of a held-out step table."""
    nan = float("nan")
    kinds = [v.code for v in grid.violations] if grid.converged else []
    exchange = (grid.external_grid_kwh or 0.0) if grid.converged else 0.0
    loading = list(grid.line_loading_percent.values()) if grid.converged else []

    def number(value: Optional[float]) -> float:
        return nan if value is None else float(value)

    return {
        "day": day,
        "step": step,
        "feed_in_tariff": float(fit),
        "utility_price": float(util),
        "max_line_loading_percent": number(grid.max_line_loading_percent),
        "max_trafo_loading_percent": number(grid.max_trafo_loading_percent),
        "min_voltage_pu": number(grid.min_voltage_pu),
        "max_voltage_pu": number(grid.max_voltage_pu),
        "mean_line_loading_percent": float(np.mean(loading)) if loading else nan,
        "grid_import_kwh": max(exchange, 0.0),
        "grid_export_kwh": max(-exchange, 0.0),
        "grid_losses_kwh": float(grid.losses_kwh or 0.0) if grid.converged else 0.0,
        "voltage_violations": float(sum(k in ("V_LOW", "V_HIGH") for k in kinds)),
        "loading_violations": float(
            sum(k in ("LINE_OVERLOAD", "TRAFO_OVERLOAD") for k in kinds)
        ),
        "not_converged": 0.0 if grid.converged else 1.0,
        "fees": float(sum(t.fees for t in settled)) if fees else nan,
        "loss_charge": float(sum(charges.values())),
        "p2p_kwh": 0.0,
        "peer_price": nan,
    }


def _reference_days(steps: pd.DataFrame, policy: str) -> pd.DataFrame:
    """A reference's flow steps (``_flows``) as the grid columns of the day table: the
    indicators a played policy's step table gives (``indicators._step_indicators``) and
    the day's sums of the exchange, losses, not converged steps, fees and loss charge,
    indexed ``(policy, day)``."""
    found = steps.assign(policy=policy)
    grid = indicators._step_indicators(found)
    sums = found.groupby(indicators.KEYS)[
        [
            "grid_import_kwh",
            "grid_export_kwh",
            "grid_losses_kwh",
            "not_converged",
            "fees",
            "loss_charge",
        ]
    ].sum(min_count=1)

    return grid.join(sums)


# --------------------------------------------------------------------------------------
# The references of a run's test periods
# --------------------------------------------------------------------------------------
class References(NamedTuple):
    """A run's references, from its held-out tables (``references``).

    Attributes:
        ceiling: The ceiling, a row per test day of the policy ``ceiling``.
        alone: The non-P2P reference per participant and day.
        alone_team: The non-P2P reference as a policy of the day table, a row per day.
        by_day: ``(ceiling, alone)`` with every test day its own horizon
            (``day_references``).
    """

    ceiling: Optional[pd.DataFrame]
    alone: Optional[pd.DataFrame]
    alone_team: Optional[pd.DataFrame]
    by_day: tuple


def references(
    agent_steps: Optional[pd.DataFrame],
    steps: Optional[pd.DataFrame],
    scenario: Optional[Mapping[str, Any]],
    grid: bool = True,
) -> References:
    """The ceiling, the non-P2P reference and the per-day references of a run, from its
    held-out tables (see ``ceiling_days``, ``alone_days``, ``day_references``). With
    ``grid`` the first two get the power flow and, for non-P2P, the fees; ``grid`` off
    (or a scenario too short to build the market) leaves them as money only."""
    market = _market_of(scenario) if grid else None
    top = _ceiling(agent_steps, steps, scenario, market)
    alone, team = _alone(agent_steps, steps, scenario, market)

    return References(top, alone, team, day_references(agent_steps, steps, scenario))


def reference_key(
    agent_steps: Optional[pd.DataFrame],
    steps: Optional[pd.DataFrame],
    scenario: Optional[Mapping[str, Any]],
) -> Optional[str]:
    """A digest of exactly what ``references`` reads, so two runs with the same digest
    have the same references: the scenario, one policy's profiles and tariffs (every
    policy has the same), and each battery's start state, rounded (it is the first
    row's ``soc`` less its change, which the learning policy's actions move in the
    last decimals only). The same scenario and test days played by several seeds,
    paradigms or algorithms share one. ``None`` without the tables or the scenario."""
    if agent_steps is None or steps is None or not scenario or "policy" not in agent_steps:
        return None

    policy = agent_steps.policy.iloc[0]
    mine = agent_steps[agent_steps.policy == policy]
    tariffs = steps[steps.policy == policy] if "policy" in steps else steps
    profiles = ["period", "day", "step", "agent", "generation_kwh", "demand_kwh"]
    prices = ["period", "day", "step", "feed_in_tariff", "utility_price"]
    starts = [
        round(store.start_kwh, 6)
        for _, _, _, stores in _periods(agent_steps, steps, scenario)
        for store in stores.values()
    ]
    digest = hashlib.sha1(json.dumps(scenario, sort_keys=True, default=str).encode())

    for table, columns in ((mine, profiles), (tariffs, prices)):
        found = table[[c for c in columns if c in table]]
        digest.update(pd.util.hash_pandas_object(found, index=False).to_numpy().tobytes())

    digest.update(json.dumps(starts).encode())

    return digest.hexdigest()


def ceiling_days(
    agent_steps: Optional[pd.DataFrame],
    steps: Optional[pd.DataFrame],
    scenario: Optional[Mapping[str, Any]],
    grid: bool = True,
) -> Optional[pd.DataFrame]:
    """The ceiling of every test period of a run, from its held-out tables: a row per
    test day (policy ``ceiling``) with ``energy_money`` (the program's value, before
    any grid fee and loss charge) and ``stored_change_kwh``. One planner for the whole
    community, its batteries ending at least as full as they started. ``None``
    without the tables, the scenario or a period.

    With ``grid`` the schedule also runs through the market's power flow (the same
    network, background and scales, ``_flows``): the day's losses, violations, loadings,
    voltages, exchange and ``loss_charge`` (the participants' shares of the losses
    under the scenario's rule, at the utility price). ``fees`` and ``team_money``, the
    money after fees, stay NaN: the program nets the whole community, so who traded
    with whom, which a fee needs, is undefined.

    Args:
        agent_steps: ``heldout_agent_steps``: generation, demand, the batteries'
            state of charge and change per participant and step.
        steps: ``heldout_steps``: the tariffs per step.
        scenario: The run's scenario (``scenario.json``), for the batteries and the
            network.
        grid: Run the power flow on the schedule.
    """
    market = _market_of(scenario) if grid else None

    return _ceiling(agent_steps, steps, scenario, market)


def _ceiling(
    agent_steps: Optional[pd.DataFrame],
    steps: Optional[pd.DataFrame],
    scenario: Optional[Mapping[str, Any]],
    market: Any,
) -> Optional[pd.DataFrame]:
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
        day = day.rename(columns={"money": "energy_money"})
        day["team_money"] = np.nan  # after fees: who traded with whom is undefined
        day = day.assign(policy=POLICY).set_index(indicators.KEYS)

        if market is not None:
            owners = list(stores)
            schedule = [
                pd.DataFrame(table.to_numpy(), net.index, columns=owners)
                for table in (plan.charge, plan.discharge)
            ]
            flows, _ = _flows(market, days, net.index, prices, part, *schedule, False)
            day = day.join(_reference_days(flows, POLICY))

        found.append(day.reset_index())

    if not found:
        return None

    return pd.concat(found, ignore_index=True).set_index(indicators.KEYS)


def alone_days(
    agent_steps: Optional[pd.DataFrame],
    steps: Optional[pd.DataFrame],
    scenario: Optional[Mapping[str, Any]],
    grid: bool = True,
) -> Optional[pd.DataFrame]:
    """The non-P2P reference of Zhou et al. (2018, §4.1): every participant on its
    own with the retailer, its own battery timed with perfect foresight of its own
    profiles and the tariffs over the test period, ending at least as full as it
    started (their A15), no netting with anyone. A participant without a battery has
    nothing to choose: its surplus at the feed-in tariff, its deficit at the utility
    price. A row per day and participant: ``period``, ``energy_bill`` (the program's
    money, before fees), ``fees`` and ``loss_charge``, ``bill`` (after them) and
    ``stored_change_kwh``.

    Every participant's exchange with the retailer is a settlement with the DSO, so with
    ``grid`` it is charged exactly as the market charges the energy no trade covers
    (``LocalEnergyMarket.assess_outcomes``): the fees of a DSO trade along its path to
    the transformer, and its share of the losses of the power flow of all of them
    together. Without ``grid`` (or a scenario too short to build the market) ``bill`` is
    ``energy_bill`` and the fees are NaN.

    Args:
        agent_steps: ``heldout_agent_steps``, as for ``ceiling_days``.
        steps: ``heldout_steps``, the tariffs per step.
        scenario: The run's scenario, for the batteries and the network.
        grid: Run the power flow and the fees.
    """
    market = _market_of(scenario) if grid else None

    return _alone(agent_steps, steps, scenario, market)[0]


def _alone(
    agent_steps: Optional[pd.DataFrame],
    steps: Optional[pd.DataFrame],
    scenario: Optional[Mapping[str, Any]],
    market: Any,
) -> tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """``(per participant and day, the team as a policy of the day table)``."""
    hours = float((scenario or {}).get("grid", {}).get("step_hours", 1.0))
    found, teams = [], []

    for days, part, prices, stores in _periods(agent_steps, steps, scenario):
        period = part.period.iloc[0]
        at = pd.MultiIndex.from_frame(part[["_d", "step"]].drop_duplicates())
        rows, charge, discharge = [], {}, {}

        for agent, own in part.groupby("agent", sort=False):
            net = (own.generation_kwh - own.demand_kwh).to_numpy()
            own_at = pd.MultiIndex.from_frame(own[["_d", "step"]])
            store = [stores[agent]] if agent in stores else []
            plan = optimise(
                net,
                prices.feed_in_tariff.reindex(own_at).to_numpy(),
                prices.utility_price.reindex(own_at).to_numpy(),
                store,
                hours,
            )
            start = store[0].start_kwh if store else 0.0
            day = _by_day(plan, days, own_at, start)
            rows.append(
                day.rename(columns={"money": "energy_bill"}).assign(
                    agent=agent, period=period
                )
            )

            if store:
                charge[agent] = pd.Series(plan.charge.iloc[:, 0].to_numpy(), own_at)
                discharge[agent] = pd.Series(plan.discharge.iloc[:, 0].to_numpy(), own_at)

        people = pd.concat(rows, ignore_index=True)
        flows = None

        if market is not None:
            frames = [
                pd.DataFrame(table).reindex(at).fillna(0.0)
                for table in (charge, discharge)
            ]
            flows, each = _flows(market, days, at, prices, part, *frames, True)
            own_fees = each.groupby(["day", "agent"])[["fees", "loss_charge"]].sum()
            people = people.join(own_fees, on=["day", "agent"])
        else:
            people["fees"] = people["loss_charge"] = np.nan

        people["bill"] = (
            people.energy_bill - people.fees.fillna(0.0) - people.loss_charge.fillna(0.0)
        )
        found.append(people)
        team = people.groupby("day", sort=False).agg(
            energy_money=("energy_bill", "sum"),
            team_money=("bill", "sum"),
            stored_change_kwh=("stored_change_kwh", "sum"),
        )
        team.index = pd.MultiIndex.from_product(
            [[indicators.NON_P2P], team.index], names=indicators.KEYS
        )

        if flows is not None:
            team = team.join(_reference_days(flows, indicators.NON_P2P))

        teams.append(team)

    if not found:
        return None, None

    return pd.concat(found, ignore_index=True), pd.concat(teams)


def day_references(
    agent_steps: Optional[pd.DataFrame],
    steps: Optional[pd.DataFrame],
    scenario: Optional[Mapping[str, Any]],
) -> tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """The ceiling and the non-P2P reference with every test day its own horizon, as
    Zhou et al. (2018) evaluate one day: each battery starts the day at the scenario's
    initial charge and ends it at least as full. Returns ``(ceiling, alone)``: the
    ceiling's ``energy_money`` per day (indexed like ``ceiling_days``), and each
    participant's own optimum per day (``day``, ``agent``, ``bill``, which is
    ``energy_bill``: before fees, as the ceiling). The policies'
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

    setups = _batteries(scenario)
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
        tops.append({"policy": POLICY, "day": day, "energy_money": top.value})

        for agent, own in part.groupby("agent", sort=False):
            mine_net = (own.generation_kwh - own.demand_kwh).to_numpy()
            store = [stores[agent]] if agent in stores else []
            value = optimise(mine_net, fit, util, store, hours).value
            alone.append(
                {"day": day, "agent": agent, "bill": value, "energy_bill": value}
            )

    if not tops:
        return None, None

    return pd.DataFrame(tops).set_index(["policy", "day"]), pd.DataFrame(alone)
