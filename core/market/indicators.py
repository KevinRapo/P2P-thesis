"""What is computed from a run's saved tables: indicators, and comparisons of runs.

Nothing here is recorded, so all of it can change and still apply to finished runs.

    INDICATORS            what is reported: name, unit, tab
    day_table(...)        one run: a row per policy and test day, a column per indicator
    side_by_side(...)     any runs: an indicator per row, over the seeds
    against_baseline(...) any runs: each value minus the run's own baseline
    difference(...)       any runs: the difference from a reference, paired if it can be

The comparisons read the long table of ``results.day_indicators``: a row per run,
policy, test day and indicator, with what the run was (``FACTORS``). They refuse
nothing: what is comparable is for the reader to judge from what differs.

The spread is over seeds. A seed is one number, its mean over the test days: days are
not independent, and every seed plays the same ones, so they never go into an interval.
Below ``INTERVAL_SEEDS`` seeds a row shows each seed's value instead of an interval.

**Which money.** A participant's bill is what its trades and its untraded energy earn
and cost, less the grid fees it pays and its loss charge. Two moneys come from it:

    energy_money   the bill before grid fees and loss charge: the energy at its prices.
                   The peer charge is not energy money: it is paid to the DSO on top of
                   the price, so it counts with the fees (0 in the thesis scenario).
    team_money     the bill after fees and loss charge: energy_money - fees -
                   loss_charge, the participants together.

The two references (``ceiling.py``) are linear programs on energy: their money is
``energy_money``. So the VTI is on ``energy_money``, the same money on both sides, and
``vti_after_fees`` puts the policy's ``team_money`` against the same references: their
difference is the value the fees and the loss charge take off. The participants'
scores (``participants_better``, ``worst_participant_gain``, PI, EI) compare bills
after fees with the non-P2P bills after fees (``ceiling.alone_days`` charges them), so
they use real money on both sides; the per-day PI and EI use energy money, as the
per-day references have no fees.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
import pandas as pd

TRAINED = "trained"
# The two outer references, computed rather than played (``ceiling.py``): every
# participant on its own with the retailer, its battery timed with perfect foresight,
# and the most money the test period allows. Between them the one played baseline,
# the market's bidding rule.
NON_P2P = "non_p2p"
NET_POSITION = "net_position"
CEILING = "ceiling"
KEYS = ["policy", "day"]
DSO = "DSO"  # core.market.dso.DSO_ID (a test compares them), like ``KPIS`` below
# What a run can differ in. ``variant`` and ``experiment`` name versions, so they do
# not split a difference; the others do (``difference``).
FACTORS = (
    "paradigm",
    "reward",
    "observation",
    "prices",
    "peer_charge",
    "network",
)
# What the baselines depend on, as far as a run says.
PLAYED_ON = (
    "prices",
    "peer_charge",
    "network",
    "test_days",
    "participants",
    "participant_set",
    "batteries",
)
INTERVAL_SEEDS = 5
BOOTSTRAPS = 2000
# Kept in step with core.market.signals.KPIS (a test compares them): importing it here
# would load the market just to read a table.
KPIS = (
    "social_welfare",
    "liquidity",
    "bid_ask_spread",
    "price_volatility",
    "supply_demand_imbalance",
    "grid_congestion",
    "coordination_score",
    "coordination_convergence",
    "der_self_consumption",
    "flexibility_utilization",
)


# --------------------------------------------------------------------------------------
# What is reported
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Indicator:
    """One number per run, policy and test day.

    Attributes:
        name: Its column.
        label: What the Studio calls it.
        unit: Its unit.
        tab: The Results tab that reports it.
        headline: A column of the overview table.
    """

    name: str
    label: str
    unit: str
    tab: str
    headline: bool = False


INDICATORS = (
    # Validation: is it worth anything?
    Indicator("energy_money", "Energy money, before fees", "EUR", "validation", True),
    Indicator("team_money", "Team money, after fees", "EUR", "validation", True),
    # Over the test period, the same on each of its days (``_period_scores``)
    Indicator("vti", "VTI, on energy money", "", "validation", True),
    Indicator("vti_after_fees", "VTI, after fees", "", "validation", True),
    Indicator("pi", "PI", "", "validation", True),
    Indicator("ei", "EI", "", "validation", True),
    # The same per test day, each day its own horizon (``_day_scores``)
    Indicator("vti_day", "VTI, per day, on energy money", "", "validation"),
    Indicator("vti_day_after_fees", "VTI, per day, after fees", "", "validation"),
    Indicator("pi_day", "PI, per day", "", "validation"),
    Indicator("ei_day", "EI, per day", "", "validation"),
    Indicator(
        "gain_net_position", "Gain over net position, after fees", "EUR", "validation", True
    ),
    Indicator("stored_change_kwh", "Stored change", "kWh", "validation", True),
    Indicator(
        "participants_better",
        "Better off than alone, after fees",
        "participants",
        "validation",
    ),
    Indicator(
        "worst_participant_gain",
        "Worst participant's gain, after fees",
        "EUR",
        "validation",
    ),
    # Market: how was the energy traded?
    Indicator("p2p_kwh", "Peer energy", "kWh", "market", True),
    Indicator("trading_ratio", "Trading ratio", "", "market", True),
    Indicator("unmet_kwh", "Unmet demand", "kWh", "market", True),
    Indicator("peer_trades", "Peer trades", "trades", "market"),
    Indicator("mean_trade_kwh", "Mean peer trade", "kWh", "market"),
    Indicator("market_concentration", "Market concentration", "", "market"),
    Indicator("buyer_gain", "Buyers' gain", "EUR", "market"),
    Indicator("seller_gain", "Sellers' gain", "EUR", "market"),
    Indicator("dso_money", "DSO money", "EUR", "market"),
    Indicator("self_sufficiency", "Self-sufficiency", "", "market"),
    Indicator("spilled_kwh", "Spilled supply", "kWh", "market"),
    Indicator("bought_from_dso_kwh", "Bought from DSO", "kWh", "market"),
    Indicator("sold_to_dso_kwh", "Sold to DSO", "kWh", "market"),
    Indicator("preference_kwh", "Stage 1 energy", "kWh", "market"),
    Indicator("local_coverage", "Local coverage", "", "market"),
    Indicator("mean_peer_price", "Mean peer price", "EUR/kWh", "market"),
    Indicator("peer_price_position", "Peer price in the band", "", "market"),
    Indicator("fees", "Grid fees", "EUR", "market"),
    Indicator("loss_charge", "Loss charge", "EUR", "market"),
    Indicator("peer_charge", "Peer charge", "EUR", "market"),
    Indicator("battery_throughput_kwh", "Battery throughput", "kWh", "market"),
    Indicator("end_reputation", "Reputation at the end", "", "market"),
    Indicator("no_order_share", "No-order share", "", "market"),
    Indicator("buy_share", "Buy share", "", "market"),
    Indicator("sell_share", "Sell share", "", "market"),
    *(Indicator(k, k.replace("_", " "), "", "market") for k in KPIS),
    # Grid: what did it do to the network?
    Indicator("highest_line_loading", "Highest line loading", "%", "grid", True),
    Indicator("hours_over_limit", "Hours over a limit", "h", "grid", True),
    Indicator("hours_voltage_limit", "Hours over a voltage limit", "h", "grid"),
    Indicator("hours_loading_limit", "Hours over a loading limit", "h", "grid"),
    Indicator("highest_trafo_loading", "Highest transformer loading", "%", "grid"),
    Indicator("lowest_voltage", "Lowest voltage", "pu", "grid"),
    Indicator("highest_voltage", "Highest voltage", "pu", "grid"),
    Indicator("grid_import_kwh", "Upstream import", "kWh", "grid"),
    Indicator("grid_export_kwh", "Upstream export", "kWh", "grid"),
    Indicator("peak_import_kw", "Peak import", "kW", "grid"),
    Indicator("peak_export_kw", "Peak export", "kW", "grid"),
    Indicator("load_factor", "Load factor", "", "grid"),
    Indicator("peak_reduction_kw", "Peak reduction against net position", "kW", "grid"),
    Indicator("mean_line_loading", "Mean line loading", "%", "grid"),
    Indicator("grid_losses_kwh", "Losses", "kWh", "grid"),
    Indicator("trade_losses_kwh", "Trade losses", "kWh", "grid"),
    Indicator("trade_loss_ratio", "Trade loss ratio", "", "grid"),
    Indicator("not_converged", "Flows not converged", "steps", "grid"),
    # Zhou et al. (2018) eq. 22-28, the participants as one community
    Indicator("energy_balance_index", "Energy balance index, per day", "", "grid"),
    Indicator("peak_to_average", "Peak-to-average (EPARI), per day", "", "grid"),
    Indicator("self_sufficiency_index", "Self-sufficiency index, per day", "", "grid"),
    # The same over the test period, on each of its days: the overview's columns
    Indicator("energy_balance_index_period", "Energy balance index", "", "grid", True),
    Indicator("peak_to_average_period", "Peak-to-average (EPARI)", "", "grid", True),
    Indicator(
        "self_sufficiency_index_period", "Self-sufficiency index", "", "grid", True
    ),
)
# Amounts of a day's table that are indicators as they stand.
_COPIED = (
    "p2p_kwh",
    "bought_from_dso_kwh",
    "sold_to_dso_kwh",
    "preference_kwh",
    "fees",
    "peer_charge",
    "grid_import_kwh",
    "grid_export_kwh",
    "grid_losses_kwh",
    "trade_losses_kwh",
    "not_converged",
    "peer_trades",
    *KPIS,
)


_TEAM = (
    "bill",
    "fees",
    "loss_charge",
    "deferred_demand_kwh",
    "deferred_supply_kwh",
    "stored_change_kwh",
)


# --------------------------------------------------------------------------------------
# One run
# --------------------------------------------------------------------------------------
def day_table(
    episodes: pd.DataFrame,
    agents: pd.DataFrame,
    steps: Optional[pd.DataFrame] = None,
    agent_steps: Optional[pd.DataFrame] = None,
    trades: Optional[pd.DataFrame] = None,
    ceiling: Optional[pd.DataFrame] = None,
    alone: Optional[pd.DataFrame] = None,
    day_references: Optional[tuple] = None,
    alone_team: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """One run's ``INDICATORS``: a row per policy and test day, from its held-out
    tables. What a table of an older run does not hold stays NaN.

    ``ceiling`` (``ceiling.ceiling_days``) adds the money ceiling as a policy of its
    own: its energy money, stored change and, from its power flow, the grid columns;
    it plays no market, so everything else stays NaN, its fees and team money too (who
    traded with whom is undefined). ``alone`` (``ceiling.alone_days``: each
    participant's own optimum with the retailer, its fees charged) adds ``non_p2p``
    the same way, and is what ``participants_better`` and ``worst_participant_gain``
    compare each participant with; ``alone_team`` (the non-P2P rows of the day table
    with their power flow and fees, ``ceiling.references``) fills its grid columns. With both references, every policy's VTI, PI and EI over its
    test period (``_period_scores``). ``day_references`` (``ceiling.day_references``:
    every day its own horizon) adds the same three per day (``_day_scores``:
    ``vti_day``, ``pi_day``, ``ei_day``)."""
    out = episodes.set_index(KEYS).reindex(columns=_COPIED)
    team = agents.groupby(KEYS).sum(numeric_only=True).reindex(columns=_TEAM)
    out["team_money"] = team["bill"]
    out["energy_money"] = team["bill"] + team["fees"]  # before fees and loss charge
    out["loss_charge"] = team["loss_charge"]
    out["unmet_kwh"] = team["deferred_demand_kwh"]
    out["spilled_kwh"] = team["deferred_supply_kwh"]
    out["stored_change_kwh"] = team["stored_change_kwh"]
    days = out.index.get_level_values("day")
    played = set(out.index.get_level_values("policy"))

    if NET_POSITION in played:
        base = out.team_money.xs(NET_POSITION, level="policy")
        out["gain_net_position"] = out.team_money - days.map(base)

    traded = out.p2p_kwh + out.bought_from_dso_kwh + out.sold_to_dso_kwh
    out["trade_loss_ratio"] = out.trade_losses_kwh / traded.where(traded > 0)

    if steps is not None and agent_steps is not None:
        out = out.join(_step_indicators(steps))
        out = out.join(_agent_step_indicators(steps, agent_steps))
        out = out.join(_community_indicators(agent_steps))
        if NET_POSITION in played:
            peak = out.peak_import_kw
            base = peak.xs(NET_POSITION, level="policy")
            out["peak_reduction_kw"] = days.map(base) - peak

        if trades is not None:
            out = out.join(_trade_indicators(trades, steps, agent_steps, out.index))

    if alone is not None:
        # Each participant against its own non-P2P money (on its own with the
        # retailer, its battery timed with perfect foresight), day by day.
        own = agents.set_index([*KEYS, "agent"]).bill
        floor = alone.set_index(["day", "agent"]).bill
        at = own.index.droplevel("policy")
        gains = pd.Series(own.to_numpy() - floor.reindex(at).to_numpy(), own.index)
        out["participants_better"] = (gains > 0).groupby(KEYS).sum()
        out["worst_participant_gain"] = gains.groupby(KEYS).min()

        if alone_team is not None:
            row = alone_team
        else:
            team = alone.groupby("day").bill.sum()
            energy = alone.get("energy_bill", alone.bill).groupby(alone.day).sum()
            stored = alone.groupby("day").stored_change_kwh.sum()
            row = pd.DataFrame(
                {
                    "energy_money": energy.reindex(team.index),
                    "team_money": team,
                    "stored_change_kwh": stored.reindex(team.index),
                }
            )
            row.index = pd.MultiIndex.from_product([[NON_P2P], team.index], names=KEYS)

        out = _with_reference(out, row)

    if ceiling is not None:
        out = _with_reference(out, ceiling)

    if alone is not None and ceiling is not None:
        out = out.join(_period_scores(out, agents, alone))

    if day_references is not None and day_references[0] is not None:
        out = out.join(_day_scores(out, agents, *day_references))

    return out.reindex(columns=[i.name for i in INDICATORS])


def _with_reference(out: pd.DataFrame, top: pd.DataFrame) -> pd.DataFrame:
    """``out`` with a reference's rows (a policy that plays no market), its gain over
    the played baseline added."""
    top = top.reindex(columns=out.columns)
    on = top.index.get_level_values("day")

    if NET_POSITION in set(out.index.get_level_values("policy")):
        base = out.team_money.xs(NET_POSITION, level="policy")
        top["gain_net_position"] = top.team_money - on.map(base)

    return pd.concat([out, top])


def _period_scores(
    out: pd.DataFrame, agents: pd.DataFrame, own: pd.DataFrame
) -> pd.DataFrame:
    """Every policy's VTI, PI and EI over its test period, on each day of the period.

    VTI = (energy money − non-P2P) / (ceiling − non-P2P), the period's sums: 0 is every
    participant on its own, 1 the most the period allows, all three before any grid fee
    and loss charge (the references are programs on energy). ``vti_after_fees`` is the
    same with the policy's ``team_money``, after fees, in the numerator and the same
    references: the difference is what the fees and the loss charge take off, in
    shares of the gap. Without ``energy_money`` in ``out`` the VTI is on ``team_money``.
    PI: the share of participants whose money over the period beats their own non-P2P
    money (``own.bill``, after the fees ``alone_days`` charges it). EI: how evenly the
    gains over their own non-P2P money are shared (``equality``)."""
    period_of = own.drop_duplicates("day").set_index("day").period
    money = out.reset_index()
    money["period"] = money.day.map(period_of)
    column = "energy_money" if "energy_money" in out else "team_money"
    totals = money.groupby(["period", "policy"])[column].sum().unstack("policy")
    reach = (totals[CEILING] - totals[NON_P2P]).where(lambda gap: gap > 0)
    vti = totals.sub(totals[NON_P2P], axis=0).div(reach, axis=0)

    bills = agents.assign(period=agents.day.map(period_of))
    mine = bills.groupby(["period", "policy", "agent"]).bill.sum()
    alone = own.groupby(["period", "agent"]).bill.sum()
    base = alone.reindex(mine.index.droplevel("policy")).to_numpy()
    pi = (mine > base).groupby(["period", "policy"]).mean().unstack("policy")
    gains = mine - base
    ei = gains.groupby(["period", "policy"]).agg(equality).unstack("policy")

    at = pd.MultiIndex.from_arrays(
        [out.index.get_level_values("day").map(period_of),
         out.index.get_level_values("policy")]
    )
    scores = pd.DataFrame(index=out.index)
    scores["vti"] = vti.stack().reindex(at).to_numpy()

    if "energy_money" in out and "team_money" in out:
        paid = money.groupby(["period", "policy"]).team_money.sum(min_count=1)
        after = paid.unstack("policy").sub(totals[NON_P2P], axis=0).div(reach, axis=0)
        scores["vti_after_fees"] = after.stack().reindex(at).to_numpy()

    scores["pi"] = pi.stack().reindex(at).to_numpy()
    scores["ei"] = ei.stack().reindex(at).to_numpy()

    return scores


def _day_scores(
    out: pd.DataFrame, agents: pd.DataFrame, top: pd.DataFrame, alone: pd.DataFrame
) -> pd.DataFrame:
    """Every played policy's VTI, PI and EI per test day, each day its own horizon:
    against that day's ceiling and each participant's own optimum of that day
    (``ceiling.day_references``), both before fees. So the VTI is on ``energy_money``
    (``vti_day_after_fees`` on ``team_money`` against the same references), and the
    PI and EI on each participant's energy bill, its bill plus its fees. The
    references' own rows stay NaN."""
    ceiling = (top.energy_money if "energy_money" in top else top.team_money)
    ceiling = ceiling.droplevel("policy")
    base = alone.set_index(["day", "agent"]).bill
    floor = base.groupby("day").sum()
    days = out.index.get_level_values("day")
    reach = np.where(
        (days.map(ceiling) - days.map(floor)).to_numpy() > 0,
        (days.map(ceiling) - days.map(floor)).to_numpy(),
        np.nan,
    )
    money = out.energy_money if "energy_money" in out else out.team_money
    vti = (money.to_numpy() - days.map(floor)) / reach

    energy = agents.bill + (agents.fees if "fees" in agents else 0.0)
    played = agents.assign(energy_bill=energy).set_index(["policy", "day", "agent"])
    played = played.energy_bill
    gains = played - base.reindex(played.index.droplevel("policy")).to_numpy()
    by = gains.groupby(["policy", "day"])
    scores = pd.DataFrame(
        {"pi_day": (gains > 0).groupby(["policy", "day"]).mean(), "ei_day": by.agg(equality)}
    )
    scores = scores.reindex(out.index)
    scores.insert(0, "vti_day", np.asarray(vti, dtype=float))

    if "energy_money" in out and "team_money" in out:
        after = (out.team_money.to_numpy() - days.map(floor)) / reach
        scores.insert(1, "vti_day_after_fees", np.asarray(after, dtype=float))

    reference = out.index.get_level_values("policy").isin([CEILING, NON_P2P])
    scores.loc[reference] = np.nan

    return scores


def equality(gains: Sequence[float]) -> float:
    """The equality index on gains, 1 − Gini with the absolute values in the
    denominator, so that it stays in [0, 1] when some gains are negative:

        EI = 1 − Σ_n Σ_m |x_n − x_m| / (2 N Σ_n |x_n|)

    1: everyone gained (or lost) the same; towards 0: the gain sits with few. With
    only non-negative gains it is the usual 1 − Gini. NaN when nobody gained or lost
    anything. Read it next to the VTI: equal losses score 1 too."""
    x = np.asarray(gains, dtype=float)
    scale = 2 * len(x) * np.abs(x).sum()

    if scale == 0:
        return float("nan")

    return 1.0 - np.abs(x[:, None] - x[None, :]).sum() / scale


def _step_indicators(steps: pd.DataFrame) -> pd.DataFrame:
    """What a day's market and grid steps give."""
    day = steps.groupby(KEYS)
    hours = 24.0 / day.step.count()
    over = steps.voltage_violations + steps.loading_violations > 0
    traded = steps.peer_price.notna()
    peak = day.grid_import_kwh.max()
    loading = steps.get("mean_line_loading_percent", pd.Series(np.nan, steps.index))
    volume = steps.p2p_kwh.where(traded, 0.0)
    band = (steps.peer_price - steps.feed_in_tariff) / (
        steps.utility_price - steps.feed_in_tariff
    )

    def weighted(values: pd.Series) -> pd.Series:
        total = (values.fillna(0.0) * volume).groupby([steps.policy, steps.day]).sum()

        return total / volume.groupby([steps.policy, steps.day]).sum()

    return pd.DataFrame(
        {
            "highest_line_loading": day.max_line_loading_percent.max(),
            "highest_trafo_loading": day.max_trafo_loading_percent.max(),
            "lowest_voltage": day.min_voltage_pu.min(),
            "highest_voltage": day.max_voltage_pu.max(),
            "peak_import_kw": day.grid_import_kwh.max() / hours,
            "peak_export_kw": day.grid_export_kwh.max() / hours,
            "load_factor": day.grid_import_kwh.mean() / peak.where(peak > 0),
            "mean_line_loading": loading.groupby([steps.policy, steps.day]).mean(),
            "hours_over_limit": over.groupby([steps.policy, steps.day]).sum() * hours,
            "hours_voltage_limit": (steps.voltage_violations > 0)
            .groupby([steps.policy, steps.day])
            .sum()
            * hours,
            "hours_loading_limit": (steps.loading_violations > 0)
            .groupby([steps.policy, steps.day])
            .sum()
            * hours,
            "mean_peer_price": weighted(steps.peer_price),
            "peer_price_position": weighted(band),
        }
    )


def _community_indicators(agent_steps: pd.DataFrame) -> pd.DataFrame:
    """Zhou et al. (2018)'s technical indices for the participants as one community,
    per policy and day (their eq. 22-28). Each step's community net consumption is
    the participants' demand and charging less their generation and discharging,
    netted over all of them: what the community exchanged with the upstream grid,
    without the network's other loads.

        energy_balance_index   EBI = 1 − Σ_t |net_t| / (Σ consumption + Σ production)
        peak_to_average        EPARI = max_t |net_t| / mean_t |net_t|; lower is
                               flatter. Their PFI = 1 − EPARI / EPARI_ref needs the
                               worst of the runs compared, so it is left to the
                               comparison
        self_sufficiency_index SSI = 1 − Σ_t max(net_t, 0) / Σ consumption
    """
    need = {"charge_kwh", "discharge_kwh", "demand_kwh", "generation_kwh"}

    if not need <= set(agent_steps):
        return pd.DataFrame()

    a = agent_steps.fillna({"charge_kwh": 0.0, "discharge_kwh": 0.0})
    a = a.assign(
        use=a.demand_kwh + a.charge_kwh,
        made=a.generation_kwh + a.discharge_kwh,
        period=a.period if "period" in a else "all",
    )
    step = a.groupby([*KEYS, "step"]).agg(
        use=("use", "sum"), made=("made", "sum"), period=("period", "first")
    )
    net = step.use - step.made
    flows = pd.DataFrame(
        {
            "net": net.abs(),
            "imported": net.clip(lower=0.0),
            "use": step.use,
            "made": step.made,
            "period": step.period,
        }
    )
    day = _technical(flows.groupby(KEYS))
    period = _technical(flows.reset_index().groupby(["policy", "period"]))
    on = pd.MultiIndex.from_arrays(
        [day.index.get_level_values("policy"),
         flows.period.groupby(KEYS).first().reindex(day.index).to_numpy()]
    )
    whole = period.reindex(on).set_axis(day.index).add_suffix("_period")

    return day.join(whole)


def _technical(groups) -> pd.DataFrame:
    """EBI, EPARI and SSI of each group of community steps (a day, or a period)."""
    total = groups[["net", "imported", "use", "made"]].sum()
    mean = groups.net.mean()

    return pd.DataFrame(
        {
            "energy_balance_index": 1.0 - total.net / (total.use + total.made),
            "peak_to_average": groups.net.max() / mean.where(mean > 0),
            "self_sufficiency_index": 1.0 - total.imported / total.use.where(total.use > 0),
        }
    )


def _agent_step_indicators(
    steps: pd.DataFrame, agent_steps: pd.DataFrame
) -> pd.DataFrame:
    """What the participants' steps give. ``need`` is each one's demand beyond its own
    generation and ``spare`` the opposite: what it had to get or get rid of."""
    a = agent_steps
    by_day = [a.policy, a.day]
    net = a.demand_kwh - a.generation_kwh
    need = net.clip(lower=0.0).groupby(by_day).sum()
    spare = (-net).clip(lower=0.0).groupby(by_day).sum()
    amounts = a.groupby(KEYS)[
        [
            "bought_kwh",
            "sold_kwh",
            "charge_kwh",
            "discharge_kwh",
        ]
    ].sum()
    from_grid = a.bought_kwh - a.peer_bought_kwh + a.deferred_demand_kwh
    uncovered = from_grid.clip(upper=net.clip(lower=0.0)).groupby(by_day).sum()
    supplied = from_grid.clip(upper=a.demand_kwh).groupby(by_day).sum()
    demand = a.demand_kwh.groupby(by_day).sum()
    last = a[a.step == a.step.max()].groupby(KEYS).reputation.mean()

    return pd.DataFrame(
        {
            "trading_ratio": (amounts.bought_kwh + amounts.sold_kwh) / (need + spare),
            "local_coverage": 1.0 - uncovered / need.where(need > 0),
            "self_sufficiency": 1.0 - supplied / demand.where(demand > 0),
            "battery_throughput_kwh": amounts.charge_kwh + amounts.discharge_kwh,
            "end_reputation": last,
            "no_order_share": (a.side == "none").groupby(by_day).mean(),
            "buy_share": (a.side == "buy").groupby(by_day).mean(),
            "sell_share": (a.side == "sell").groupby(by_day).mean(),
        }
    )


def _trade_indicators(
    trades: pd.DataFrame,
    steps: pd.DataFrame,
    agent_steps: pd.DataFrame,
    index: pd.Index,
) -> pd.DataFrame:
    """What the trades give, for the days of ``index``. ``buyer_gain`` and
    ``seller_gain`` are what the peer trades were worth against the DSO's tariffs (the
    buyer's net of the peer charge), ``dso_money`` the DSO's energy money, every fee
    charged and the demand left untraded, which the bill settles at the utility price
    (``reward.net_bill``): its profit. A day without trades gained 0 and has no mean
    size or concentration."""
    tariffs = steps[[*KEYS, "step", "feed_in_tariff", "utility_price"]]
    t = trades.merge(tariffs, on=[*KEYS, "step"])
    is_peer = t.stage < 3
    money = t.price * t.kwh
    energy = money.where(t.seller == DSO, -money).where(t.stage == 3, 0.0)
    t["buyer_gain"] = (t.utility_price * t.kwh - money - t.peer_charge).where(
        is_peer, 0.0
    )
    t["seller_gain"] = (money - t.feed_in_tariff * t.kwh).where(is_peer, 0.0)
    t["dso_money"] = energy + t.buyer_fee + t.seller_fee
    peer = t[is_peer]
    sellers = peer.groupby([*KEYS, "seller"]).kwh.sum()
    shares = sellers / sellers.groupby(KEYS).transform("sum")
    gains = t.groupby(KEYS)[["buyer_gain", "seller_gain", "dso_money"]].sum()
    sizes = pd.DataFrame(
        {
            "mean_trade_kwh": peer.groupby(KEYS).kwh.mean(),
            "market_concentration": (shares**2).groupby(KEYS).sum(),
        }
    )

    # The untraded energy, settled at retail (MP-1e): the DSO sells the deficit at
    # the utility price and buys the surplus at the feed-in tariff. Its fees are in
    # the trades' rows (stage 4, MP-1f), its energy money only here.
    per_step = agent_steps.groupby([*KEYS, "step"])
    drawn = per_step.deferred_demand_kwh.sum()
    tariffs = steps.set_index([*KEYS, "step"]).reindex(drawn.index)
    untraded = drawn * tariffs.utility_price

    if "deferred_supply_kwh" in agent_steps:
        untraded -= per_step.deferred_supply_kwh.sum() * tariffs.feed_in_tariff

    untraded = untraded.groupby(KEYS).sum()
    out = gains.reindex(index, fill_value=0.0).join(sizes)
    out["dso_money"] += untraded.reindex(index, fill_value=0.0)

    return out


# --------------------------------------------------------------------------------------
# Comparing runs
# --------------------------------------------------------------------------------------
def spread(values: Sequence[float]) -> dict:
    """A row's numbers over its seeds: their mean and values, and from
    ``INTERVAL_SEEDS`` on a 95% percentile bootstrap (``low``, ``high``)."""
    found = np.asarray(values, dtype=float)
    found = found[~np.isnan(found)]
    row = {"n": len(found), "values": found.round(6).tolist()}
    row |= {"mean": float(found.mean()) if len(found) else float("nan")}

    if len(found) >= INTERVAL_SEEDS:
        picks = np.random.default_rng(0).choice(found, (BOOTSTRAPS, len(found)))
        row["low"], row["high"] = np.percentile(picks.mean(axis=1), [2.5, 97.5])

    return row


def side_by_side(table: pd.DataFrame, rows: Sequence[str]) -> pd.DataFrame:
    """A row per combination of ``rows`` (any columns of ``table``) and indicator: the
    trained policy over the seeds, a seed being the mean of its runs' means."""
    rows = list(rows)
    trained = table[table.policy == TRAINED]
    each = [*dict.fromkeys([*rows, "key"]), "seed", "indicator"]
    runs = trained.groupby(each, dropna=False).value.mean()
    seeds = runs.groupby([*rows, "seed", "indicator"], dropna=False).mean()
    groups = seeds.groupby([*rows, "indicator"], dropna=False)

    return pd.DataFrame(
        [dict(zip([*rows, "indicator"], key)) | spread(part) for key, part in groups]
    )


def baselines(table: pd.DataFrame) -> pd.DataFrame:
    """The baselines: one row per policy and what they were played on, however many
    runs played them."""
    played = table[table.policy != TRAINED]
    groups = ["policy", *PLAYED_ON, "indicator"]
    runs = played.groupby([*groups, "key"], dropna=False, as_index=False).value.mean()

    return runs.groupby(groups, dropna=False, as_index=False).value.mean()


def against_baseline(
    table: pd.DataFrame, baseline: str = "net_position"
) -> pd.DataFrame:
    """``table``'s trained rows, each value minus the same run's ``baseline`` on the
    same day: comparable across scenarios, because each run plays its own."""
    index = ["key", "day", "indicator"]
    base = table[table.policy == baseline].set_index(index).value
    out = table[table.policy == TRAINED].copy()
    out["value"] -= base.reindex(pd.MultiIndex.from_frame(out[index])).to_numpy()

    return out


def difference(
    table: pd.DataFrame,
    by: str,
    reference: str,
    within: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Each level of the column ``by`` minus the ``reference`` level, per indicator,
    inside every combination of ``within`` (default: the other ``FACTORS`` that
    differ).

    ``paired`` says how: with the same seeds, days, prices, network and participants
    (``participant_set``, RP-7h), a seed's mean
    difference over the days both sides have a value for, with the spread over seeds;
    otherwise the difference of the two means, which keeps the variation between days,
    with ``n`` the seeds of the smaller side. Runs pooled on one side are averaged."""
    if within is None:
        within = [f for f in FACTORS if f != by and table[f].nunique(dropna=False) > 1]

    same = [*within, "indicator"]
    trained = table[table.policy == TRAINED]
    days = trained.groupby("key").day.agg(frozenset)
    worlds = trained.groupby("key")[["prices", "network", "participant_set"]].first()
    world = {k: (days[k], *row) for k, row in zip(worlds.index, worlds.to_numpy())}
    rows = []

    for context, part in trained.groupby(same, dropna=False):
        base = part[part[by] == reference]

        for level, side in part[part[by] != reference].groupby(by, dropna=False):
            one, other = _seed_days(side), _seed_days(base)
            played = {world[key] for key in (*side.key, *base.key)}
            paired = len(played) == 1 and set(side.seed) == set(base.seed)
            head = dict(zip(same, context)) | {by: level, "paired": paired}

            if paired:
                row = spread((one - other).groupby("seed").mean().to_numpy())
            else:
                means = one.groupby("seed").mean(), other.groupby("seed").mean()
                row = {
                    "mean": means[0].mean() - means[1].mean(),
                    "n": min(len(m) for m in means),
                }

            rows.append(head | row)

    return pd.DataFrame(rows)


def _seed_days(rows: pd.DataFrame) -> pd.Series:
    """A side's number per seed and day, over the runs it pools."""
    return rows.groupby(["seed", "day"]).value.mean()
