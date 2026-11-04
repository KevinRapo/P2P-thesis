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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
import pandas as pd

TRAINED = "trained"
# The two outer references, computed rather than played: every participant on its own
# (the ``zero`` policy, its spilled surplus sold at the feed-in tariff), and the most
# money the test period allows (``ceiling.py``).
NON_P2P = "non_p2p"
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
    "grid_method",
)
# What the baselines depend on, as far as a run says.
PLAYED_ON = (
    "prices",
    "peer_charge",
    "network",
    "grid_method",
    "test_days",
    "participants",
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
    Indicator("team_money", "Team money", "EUR", "validation", True),
    # Over the test period, the same on each of its days (``_period_scores``)
    Indicator("vti", "VTI", "", "validation", True),
    Indicator("pi", "PI", "", "validation", True),
    Indicator("gain_net_position", "Gain over net position", "EUR", "validation", True),
    Indicator("stored_change_kwh", "Stored change", "kWh", "validation", True),
    Indicator(
        "participants_better", "Better off than zero", "participants", "validation"
    ),
    Indicator("gain_zero", "Gain over zero", "EUR", "validation"),
    Indicator(
        "worst_participant_gain", "Worst participant's gain", "EUR", "validation"
    ),
    Indicator("reachable_share", "Share of the reachable gain", "", "validation"),
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
    Indicator("fees", "Fees", "EUR", "market"),
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
    Indicator("highest_trafo_loading", "Highest transformer loading", "%", "grid"),
    Indicator("lowest_voltage", "Lowest voltage", "pu", "grid"),
    Indicator("highest_voltage", "Highest voltage", "pu", "grid"),
    Indicator("grid_import_kwh", "Upstream import", "kWh", "grid"),
    Indicator("grid_export_kwh", "Upstream export", "kWh", "grid"),
    Indicator("peak_import_kw", "Peak import", "kW", "grid"),
    Indicator("peak_export_kw", "Peak export", "kW", "grid"),
    Indicator("load_factor", "Load factor", "", "grid"),
    Indicator("peak_reduction_kw", "Peak reduction (batteries)", "kW", "grid"),
    Indicator("mean_line_loading", "Mean line loading", "%", "grid"),
    Indicator("grid_losses_kwh", "Losses", "kWh", "grid"),
    Indicator("trade_losses_kwh", "Trade losses", "kWh", "grid"),
    Indicator("trade_loss_ratio", "Trade loss ratio", "", "grid"),
    Indicator("fee_error_mean", "Fee signal error, mean", "%", "grid"),
    Indicator("fee_error_worst", "Fee signal error, worst", "%", "grid"),
    Indicator("not_converged", "Flows not converged", "steps", "grid"),
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


_TEAM = ("bill", "deferred_demand_kwh", "deferred_supply_kwh", "stored_change_kwh")


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
) -> pd.DataFrame:
    """One run's ``INDICATORS``: a row per policy and test day, from its held-out
    tables. What a table of an older run does not hold stays NaN.

    ``ceiling`` (``ceiling.ceiling_days``) adds the money ceiling as a policy of its
    own: its team money, stored change and gains over the baselines; it plays no
    market, so everything else stays NaN. With the step tables, ``non_p2p`` is added
    the same way (``non_p2p_bills``), and with both, every policy's VTI and PI over
    its test period (``_period_scores``)."""
    out = episodes.set_index(KEYS).reindex(columns=_COPIED)
    team = agents.groupby(KEYS).sum(numeric_only=True).reindex(columns=_TEAM)
    out["team_money"] = team["bill"]
    out["unmet_kwh"] = team["deferred_demand_kwh"]
    out["spilled_kwh"] = team["deferred_supply_kwh"]
    out["stored_change_kwh"] = team["stored_change_kwh"]

    for baseline in ("zero", "net_position"):
        base = out.team_money.xs(baseline, level="policy")
        days = out.index.get_level_values("day")
        out[f"gain_{baseline}"] = out.team_money - days.map(base)

    own = agents.set_index([*KEYS, "agent"]).bill
    zero = own.xs("zero", level="policy").reindex(own.index.droplevel("policy"))
    better = own.to_numpy() > zero.to_numpy()
    out["participants_better"] = pd.Series(better, own.index).groupby(KEYS).sum()
    gains = pd.Series(own.to_numpy() - zero.to_numpy(), own.index)
    out["worst_participant_gain"] = gains.groupby(KEYS).min()
    traded = out.p2p_kwh + out.bought_from_dso_kwh + out.sold_to_dso_kwh
    out["trade_loss_ratio"] = out.trade_losses_kwh / traded.where(traded > 0)

    if steps is not None and agent_steps is not None:
        out = out.join(_step_indicators(steps))
        out = out.join(_agent_step_indicators(steps, agent_steps))
        gap = out.reachable_money - days.map(out.team_money.xs("zero", level="policy"))
        out["reachable_share"] = out.gain_zero / gap.where(gap > 0)
        peak = out.peak_import_kw
        out["peak_reduction_kw"] = days.map(peak.xs("zero", level="policy")) - peak

        if trades is not None:
            out = out.join(_trade_indicators(trades, steps, agent_steps, out.index))

    own = None

    if steps is not None and agent_steps is not None:
        own = non_p2p_bills(agent_steps, steps)

    if own is not None:
        team = own.groupby("day").bill.sum()
        zero = out.stored_change_kwh.xs("zero", level="policy")
        alone = pd.DataFrame(
            {"team_money": team, "stored_change_kwh": zero.reindex(team.index)}
        )
        alone.index = pd.MultiIndex.from_product([[NON_P2P], team.index], names=KEYS)
        out = _with_reference(out, alone)

    if ceiling is not None:
        out = _with_reference(out, ceiling)

    if own is not None and ceiling is not None:
        out = out.join(_period_scores(out, agents, own))

    return out.reindex(columns=[i.name for i in INDICATORS])


def _with_reference(out: pd.DataFrame, top: pd.DataFrame) -> pd.DataFrame:
    """``out`` with a reference's rows (a policy that plays no market), its gains over
    the played baselines added."""
    top = top.reindex(columns=out.columns)
    on = top.index.get_level_values("day")

    for baseline in ("zero", "net_position"):
        base = out.team_money.xs(baseline, level="policy")
        top[f"gain_{baseline}"] = top.team_money - on.map(base)

    return pd.concat([out, top])


def non_p2p_bills(
    agent_steps: pd.DataFrame, steps: pd.DataFrame
) -> Optional[pd.DataFrame]:
    """Each participant's money on its own, per test day: the ``zero`` policy (no
    orders, each battery following its owner's own balance), with the surplus it
    spilled sold at the feed-in tariff and its untraded demand bought at the utility
    price. A row per day and agent: ``period``, ``bill``. None without ``zero``."""
    need = {"deferred_demand_kwh", "deferred_supply_kwh"}
    zero = agent_steps[agent_steps.policy == "zero"]

    if zero.empty or not need <= set(zero) or "feed_in_tariff" not in steps:
        return None

    tariffs = steps[steps.policy == "zero"].set_index(["day", "step"])
    at = pd.MultiIndex.from_frame(zero[["day", "step"]])
    fit = tariffs.feed_in_tariff.reindex(at).to_numpy()
    util = tariffs.utility_price.reindex(at).to_numpy()
    money = fit * zero.deferred_supply_kwh - util * zero.deferred_demand_kwh
    period = zero.period if "period" in zero else "all"
    found = zero.assign(bill=money.to_numpy(), period=period)

    return found.groupby(["day", "agent"], as_index=False).agg(
        period=("period", "first"), bill=("bill", "sum")
    )


def _period_scores(
    out: pd.DataFrame, agents: pd.DataFrame, own: pd.DataFrame
) -> pd.DataFrame:
    """Every policy's VTI and PI over its test period, on each day of the period.

    VTI = (team money − non-P2P) / (ceiling − non-P2P), the period's sums: 0 is every
    participant on its own, 1 the most the period allows. PI: the share of
    participants whose money over the period beats their own non-P2P money."""
    period_of = own.drop_duplicates("day").set_index("day").period
    money = out.team_money.reset_index()
    money["period"] = money.day.map(period_of)
    totals = money.groupby(["period", "policy"]).team_money.sum().unstack("policy")
    reach = (totals[CEILING] - totals[NON_P2P]).where(lambda gap: gap > 0)
    vti = totals.sub(totals[NON_P2P], axis=0).div(reach, axis=0)

    bills = agents.assign(period=agents.day.map(period_of))
    mine = bills.groupby(["period", "policy", "agent"]).bill.sum()
    alone = own.groupby(["period", "agent"]).bill.sum()
    base = alone.reindex(mine.index.droplevel("policy")).to_numpy()
    pi = (mine > base).groupby(["period", "policy"]).mean().unstack("policy")

    at = pd.MultiIndex.from_arrays(
        [out.index.get_level_values("day").map(period_of),
         out.index.get_level_values("policy")]
    )
    scores = pd.DataFrame(index=out.index)
    scores["vti"] = vti.stack().reindex(at).to_numpy()
    scores["pi"] = pi.stack().reindex(at).to_numpy()

    return scores


def _step_indicators(steps: pd.DataFrame) -> pd.DataFrame:
    """What a day's market and grid steps give."""
    day = steps.groupby(KEYS)
    hours = 24.0 / day.step.count()
    error = (steps.fee_max_line_loading_percent - steps.max_line_loading_percent).abs()
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
            "fee_error_mean": error.groupby([steps.policy, steps.day]).mean(),
            "fee_error_worst": error.groupby([steps.policy, steps.day]).max(),
            "mean_peer_price": weighted(steps.peer_price),
            "peer_price_position": weighted(band),
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

    # The money of a community that nets each step perfectly, without batteries: its
    # deficit at the utility price, its surplus at the feed-in tariff, and no peer
    # charge on what it nets (the tables hold what was paid, not the rate).
    team = a.groupby([*KEYS, "step"])[["generation_kwh", "demand_kwh"]].sum()
    tariffs = steps.set_index([*KEYS, "step"])
    surplus = team.generation_kwh - team.demand_kwh
    money = surplus.clip(lower=0.0) * tariffs.feed_in_tariff.reindex(team.index)
    money += surplus.clip(upper=0.0) * tariffs.utility_price.reindex(team.index)

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
            "reachable_money": money.groupby(KEYS).sum(),
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
    energy = money.where(t.seller == DSO, -money).where(~is_peer, 0.0)
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

    drawn = agent_steps.groupby([*KEYS, "step"]).deferred_demand_kwh.sum()
    price = steps.set_index([*KEYS, "step"]).utility_price.reindex(drawn.index)
    untraded = (drawn * price).groupby(KEYS).sum()
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

    ``paired`` says how: with the same seeds, days, prices and network, a seed's mean
    difference over the days both sides have a value for, with the spread over seeds;
    otherwise the difference of the two means, which keeps the variation between days,
    with ``n`` the seeds of the smaller side. Runs pooled on one side are averaged."""
    if within is None:
        within = [f for f in FACTORS if f != by and table[f].nunique(dropna=False) > 1]

    same = [*within, "indicator"]
    trained = table[table.policy == TRAINED]
    days = trained.groupby("key").day.agg(frozenset)
    worlds = trained.groupby("key")[["prices", "network"]].first()
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
