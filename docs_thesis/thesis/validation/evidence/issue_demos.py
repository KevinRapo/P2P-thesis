"""Issue demonstrations: one small, explicit experiment per issue.

Each demo builds the smallest setup that shows the issue, then returns what the
paper (or the code's own documented intent) says should happen next to what the
original code in ``src_thesis/`` actually does. A demo *reproduces* its issue
when the two differ.

The same functions feed three things:

* ``test_issue_demos.py``: one test per demo that asserts ``actual == expected``.
  Each is marked ``xfail(strict=True)``, so the suite passes while the issue is
  present and fails loudly (XPASS) once someone fixes it. That is the signal to
  remove the xfail, close the issue in issues.md and delete its code marker.
* ``issue_demos.ipynb``: renders every demo with its explanation.
* ``SHOWABILITY``: how showable each of the 80 issues is, for the ones without a demo.

Run from the repository root with the ``marlem`` conda env.
"""

from __future__ import annotations

import copy
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import numpy as np

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src_thesis.adapters.grid.network import GridNetwork  # noqa: E402
from src_thesis.cooperation.implicit_cooperation import (
    ImplicitCooperation,
)  # noqa: E402
from src_thesis.marketplace.dso.dso import DSOAgent  # noqa: E402
from src_thesis.core.location import GridTopology  # noqa: E402
from src_thesis.environment.lem import LocalEnergyMarket  # noqa: E402
from src_thesis.marketplace.market.matching import (
    MarketConfig,
    OrderMatcher,
)  # noqa: E402
from src_thesis.marketplace.market.mechanism import ClearingMechanism  # noqa: E402
from src_thesis.core.orders import Order, Trade  # noqa: E402
from src_thesis.marketplace.market.validation import Validator  # noqa: E402
from src_thesis.environment.reward import RewardHandler  # noqa: E402
from src_thesis.agents.battery import Battery  # noqa: E402
from src_thesis.agents.der import DERAgent  # noqa: E402


# --------------------------------------------------------------------------- registry
@dataclass
class Demo:
    issue: str
    step: str
    title: str
    expected_label: str
    expected: Any
    actual: Any
    note: str = ""
    details: dict = field(default_factory=dict)

    @property
    def reproduced(self) -> bool:
        return not same(self.expected, self.actual)


REGISTRY: dict[str, Callable[[], Demo]] = {}


def demo(issue: str, step: str, title: str, expected_label: str):
    """Register ``fn`` as the demo for ``issue``.

    ``fn`` returns ``(expected, actual[, note[, details]])``.
    """

    def wrap(fn):
        def run() -> Demo:
            out = fn()
            expected, actual, *rest = out
            note = rest[0] if rest else ""
            details = rest[1] if len(rest) > 1 else {}
            return Demo(
                issue, step, title, expected_label, expected, actual, note, details
            )

        run.__name__ = fn.__name__
        run.title = title
        run.__wrapped__ = fn
        REGISTRY[issue] = run
        return run

    return wrap


def same(a: Any, b: Any) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        try:
            return math.isclose(float(a), float(b), rel_tol=1e-6, abs_tol=1e-9)
        except (TypeError, ValueError):
            return False
    return a == b


def run_all() -> list[Demo]:
    return [REGISTRY[k]() for k in sorted(REGISTRY)]


# ------------------------------------------------------------------------ shared setups
def market_config(**kw) -> MarketConfig:
    base = dict(
        min_price=10.0,
        max_price=300.0,
        min_quantity=0.1,
        max_quantity=100.0,
        price_mechanism=ClearingMechanism.AVERAGE,
        blockchain_difficulty=1,
    )
    base.update(kw)
    return MarketConfig(**base)


def make_env(
    n: int = 3,
    max_steps: int = 24,
    seed: int | None = 7,
    battery: bool = True,
    capacities: list[float] | None = None,
    ids: list[str] | None = None,
    **cfg,
) -> LocalEnergyMarket:
    """Small environment: flat profiles G = 10, D = 20, mesh grid, battery on a0."""
    ids = ids or [f"a{i}" for i in range(n)]
    capacities = capacities or [60.0] * len(ids)
    agents = [
        DERAgent(
            aid,
            cap,
            battery=Battery(50, 0.1, 0.9, 0.95, 0.95) if (battery and k == 0) else None,
            generation_profile=[10.0] * max_steps,
            demand_profile=[20.0] * max_steps,
        )
        for k, (aid, cap) in enumerate(zip(ids, capacities))
    ]
    grid = GridNetwork(GridTopology.MESH, max(len(ids), 2), 300.0, seed=1)
    return LocalEnergyMarket(
        {
            "max_steps": max_steps,
            "market_config": cfg.pop("market_config", market_config()),
            "agents": agents,
            "grid_network": grid,
            "seed": seed,
            **cfg,
        }
    )


def run_episode(
    env: LocalEnergyMarket, seed: int = 7, on_step: Callable | None = None
) -> int:
    """Reset, then step with seeded random actions until the episode terminates.

    Returns the number of steps executed.
    """
    env.reset(seed=seed)
    for i, aid in enumerate(env.agents_id):
        env.action_spaces[aid].seed(i)
    steps = 0
    while True:
        out = env.step({aid: env.action_spaces[aid].sample() for aid in env.agents_id})
        steps += 1
        if on_step:
            on_step(env, out)
        if out[2]["__all__"] or steps > 10 * env.max_steps:
            return steps


def matcher(located: bool = False, n_agents: int = 2):
    """An OrderMatcher on a 4-node line grid with a DSO (FiT 40, utility 250).

    With ``located=True``, agents a0 and a1 are placed on the two end nodes.
    """
    np.random.seed(0)
    grid = GridNetwork(GridTopology.LINE, 4, 300.0, seed=1)
    dso = DSOAgent("DSO", [40.0] * 24, [250.0] * 24, grid)
    m = OrderMatcher(n_agents, market_config(), grid, dso)
    locs = {}
    if located:
        a0, a1 = DERAgent("a0", 60.0), DERAgent("a1", 60.0)
        a0.node_id, a1.node_id = list(grid.graph.nodes)[0], list(grid.graph.nodes)[-1]
        grid.assign_agents_to_graph([a0, a1])
        locs = {"a0": a0.location, "a1": a1.location}
    return m, grid, dso, locs


def order(
    agent: str,
    price: float,
    qty: float,
    buy: bool,
    locs: dict | None = None,
    partner: str | None = None,
) -> Order:
    loc = (locs or {}).get(agent)
    return Order(f"{agent}_o", agent, price, qty, buy, 0.0, loc, partner)


# ====================================================================== A1 episode loop
@demo(
    "I-01",
    "A1",
    "An episode runs 23 of 24 periods",
    "steps per episode with max_steps = 24",
)
def i01():
    return 24, run_episode(make_env())


@demo(
    "I-02",
    "A1",
    "The terminal flag never reaches the reward",
    "reward calls with is_terminal=True per episode (one per agent at the last step)",
)
def i02():
    env = make_env()
    seen = []
    orig = env.reward_handler.calculate_reward

    def spy(*a, **kw):
        seen.append(kw.get("is_terminal", False))
        return orig(*a, **kw)

    env.reward_handler.calculate_reward = spy
    run_episode(env)
    return len(env.agents_id), sum(seen)


@demo(
    "I-03",
    "A1",
    "reset(seed=None) replays the same episode",
    "two resets without a seed give different episodes",
)
def i03():
    env = make_env(seed=7)
    env.reset()
    first = list(env._agents["a0"].generation_profile)
    env.reset()
    second = list(env._agents["a0"].generation_profile)
    return (
        "different",
        "identical" if first == second else "different",
        "The configured seed 7 is reused on every reset, so a training run sees one "
        "episode over and over.",
    )


@demo("I-04", "A1", "env.seed() cannot be called", "env.seed is callable")
def i04():
    env = make_env()
    return (
        True,
        callable(env.seed),
        f"env.seed is {env.seed!r}: the attribute set in __init__ shadows the method.",
    )


@demo(
    "I-78",
    "A1",
    "An invalid action crashes the step",
    "Alg. 1 drops the invalid order and the step completes",
)
def i78():
    env = make_env()
    env.reset(seed=7)
    acts = {aid: env.action_spaces[aid].sample() for aid in env.agents_id}
    acts["a0"] = np.array(
        [100.0, 5.0, 1.0, 99.0], dtype=np.float32
    )  # partner index 99 is outside the space
    try:
        env.step(acts)
        return "step completes", "step completes"
    except ValueError as e:
        return "step completes", "ValueError", str(e)


# =========================================================================== A2 inputs
@demo(
    "I-05",
    "A2",
    "Profiles given to an agent are replaced at reset",
    "agent a0 keeps its configured generation profile (10 kWh every period)",
)
def i05():
    env = make_env()
    env.reset(seed=7)
    g = env._agents["a0"].generation_profile
    return (
        [10.0] * 6,
        [round(float(x), 1) for x in g[:6]],
        "First 6 of 24 periods. The profile handler regenerates every agent's "
        "profiles on each reset.",
    )


# =================================================================== A3 action -> order
@demo(
    "I-08",
    "A3",
    "Order size does not follow eq. 15",
    "q_buy,max = max(0, D − G) + (SoC_max − SoC)·C = 25 + 50 = 75",
)
def i08():
    bat = Battery(100, 0.0, 1.0, 1.0, 1.0)
    bat.energy_level = 50.0
    ag = DERAgent(
        "t", 60.0, battery=bat, generation_profile=[5.0], demand_profile=[30.0]
    )
    adj = ag.adjust_action_for_battery(
        0, np.array([100.0, 100.0, 1.0, 0.0]), market_config()
    )
    return (
        75.0,
        float(adj[1]),
        "Request: buy 100 with G = 5, D = 30, 50 kWh free in the battery. The code "
        "subtracts G and a discharge from the *request*.",
    )


@demo(
    "I-09",
    "A3",
    "α = 0.3 is sized as a buy but submitted as a sell",
    "direction used for sizing = direction submitted",
)
def i09():
    ag = DERAgent("u", 60.0, generation_profile=[5.0], demand_profile=[30.0])
    adj = ag.adjust_action_for_battery(
        0, np.array([100.0, 40.0, 0.3, 0.0]), market_config()
    )
    sized = (
        "buy" if adj[2] else "sell"
    )  # adjust_action_for_battery: `if is_buy:` (truthy)
    submitted = (
        "buy" if adj[2] > 0.5 else "sell"
    )  # LocalEnergyMarket.step: `is_buy > 0.5`
    return (
        ("sell", "sell"),
        (sized, submitted),
        f"The agent (deficit of 25 kWh) submits a *sell* order of {adj[1]:.1f} kWh.",
    )


@demo(
    "I-10",
    "A3",
    "β = 'no preference' is practically unreachable",
    "share of uniformly sampled β that means 'no preference' (1 of N + 2 choices)",
)
def i10():
    n = 3
    beta = np.random.default_rng(0).uniform(0, n + 1, 100_000)
    share = float(np.mean(beta.astype(int) == n + 1))
    return (
        round(1 / (n + 2), 3),
        round(share, 3),
        "int(β) equals N + 1 only when β hits the upper bound exactly.",
    )


@demo(
    "I-11",
    "A3",
    "An agent can never submit 'no order'",
    "quantity after clipping when the policy asks for 0",
)
def i11():
    ag = DERAgent("v", 60.0, generation_profile=[20.0], demand_profile=[20.0])
    adj = ag.adjust_action_for_battery(
        0, np.array([100.0, 0.0, 1.0, 0.0]), market_config(min_quantity=0.1)
    )
    return (
        0.0,
        round(float(adj[1]), 3),
        "With q_min > 0 every agent trades every period; the paper has no no-trade "
        "action.",
    )


@demo(
    "I-77",
    "A3",
    "Rule-based partner choice is random",
    "distinct partners chosen in 50 calls with an unchanged state (a weighted score "
    "picks one)",
)
def i77():
    env = make_env(n=4)
    env.reset(seed=7)
    a0 = env._agents["a0"]
    picks = {
        a0.select_preferred_partner(
            [*env._agents.values()], env.grid_network.graph, randomize=True
        )
        for _ in range(50)
    }
    return 1, len(picks), f"Picked: {sorted(picks)}"


# =========================================================================== A4 pricing
@demo(
    "I-13",
    "A4",
    "Pay-as-bid (seller) returns the buyer's price",
    "trade price = p_sell = 50 (buy 200, sell 50)",
)
def i13():
    b, s = order("b", 200.0, 1.0, True), order("s", 50.0, 1.0, False)
    return (
        50.0,
        ClearingMechanism.SELLER.get_instance().calculate_price(b, s, 100.0),
        "The matcher passes (buy, sell, market_price); SellerPricing's first "
        "parameter is named sell_order.",
    )


@demo(
    "I-17",
    "A4",
    "Bid-ask spread pricing returns the buyer's price",
    "p_sell + factor·(p_buy − p_sell) with the default factor 0.5 = 125",
)
def i17():
    b, s = order("b", 200.0, 1.0, True), order("s", 50.0, 1.0, False)
    return (
        125.0,
        ClearingMechanism.BID_ASK_SPREAD.get_instance().calculate_price(b, s, 100.0),
        "market_price = 100 lands in `factor` and is clipped to 1. [P1] Case 5 uses "
        "this mechanism.",
    )


# ========================================================================== A5 matching
@demo(
    "I-12",
    "A5",
    "Matching overwrites the submitted order",
    "order.quantity after matching = submitted 10",
)
def i12():
    m, *_ = matcher()
    b = order("a0", 200.0, 10.0, True)
    m.match_orders(0, [b, order("a1", 50.0, 10.0, False)], {}, 0.0)
    return 10.0, b.quantity, "The reward, KPIs and info read this field after matching."


@demo(
    "I-14",
    "A5",
    "The P2P loss is bought again from the DSO",
    "energy the buyer is billed for = 10 (paper: the loss derates what is delivered)",
)
def i14():
    m, grid, dso, locs = matcher(located=True)
    res = m.match_orders(
        0,
        [order("a0", 200.0, 10.0, True, locs), order("a1", 50.0, 10.0, False, locs)],
        {},
        0.0,
    )
    bought = sum(t.quantity for t in res.trades if t.buyer_id == "a0")
    loss = sum(t.transmission_loss for t in res.trades)
    return (
        10.0,
        round(bought, 4),
        f"P2P loss {loss:.3f} kWh is re-bought from the DSO at the utility price.",
        {
            "trades": [
                (t.seller_id, t.buyer_id, t.quantity, t.price) for t in res.trades
            ]
        },
    )


@demo(
    "I-15",
    "A5",
    "Stage 1 sends DSO-preferred orders to the DSO first",
    "a buyer at 200 and a seller at 50 trade P2P (only mutual preferences go first)",
)
def i15():
    m, *_ = matcher()
    res = m.match_orders(
        0,
        [order("a0", 200.0, 10.0, True, partner="DSO"), order("a1", 50.0, 10.0, False)],
        {},
        0.0,
    )
    kinds = sorted(
        "P2P" if "DSO" not in (t.buyer_id, t.seller_id) else "DSO" for t in res.trades
    )
    return (
        ["P2P"],
        kinds,
        "Both sides trade with the DSO at its tariffs although a P2P match at 125 "
        "was available.",
    )


@demo(
    "I-16",
    "A5",
    "The clearing price mixes P2P and DSO trades",
    "clearing price = the P2P price 125",
)
def i16():
    m, *_ = matcher()
    res = m.match_orders(
        0, [order("a0", 200.0, 20.0, True), order("a1", 50.0, 10.0, False)], {}, 0.0
    )
    return (
        125.0,
        res.clearing_price,
        "10 kWh P2P at 125 plus 10 kWh from the DSO at 250 → volume-weighted 187.5.",
    )


@demo(
    "I-54",
    "A5",
    "DSO trades skip all grid terms",
    "fees on a DSO trade of the same seller > 0 (the grid is used either way)",
)
def i54():
    m, grid, dso, locs = matcher(located=True)
    p2p = m.match_orders(
        0,
        [order("a0", 200.0, 10.0, True, locs), order("a1", 50.0, 10.0, False, locs)],
        {},
        0.0,
    )
    m2, _, _, locs2 = matcher(located=True)
    only = m2.match_orders(0, [order("a1", 50.0, 10.0, False, locs2)], {}, 0.0)
    t_dso = only.trades[0]
    p2p_fee = next(t.fees for t in p2p.trades if "DSO" not in (t.buyer_id, t.seller_id))
    return (
        "fees > 0",
        "fees > 0" if t_dso.fees > 0 else "0 (distance, loss, fee all 0)",
        f"The same 10 kWh sold P2P carries fees {p2p_fee:.2f}; sold to the DSO: "
        f"distance {t_dso.distance}, loss {t_dso.transmission_loss}, fees "
        f"{t_dso.fees}.",
    )


@demo(
    "I-55",
    "A5",
    "The Stage-2 capacity limit is not the grid capacity",
    "capacity used by the Stage-2 check = grid capacity 300",
)
def i55():
    m, grid, *_ = matcher()
    return (
        grid.capacity,
        m.grid_capacity,
        "The matcher uses max_quantity · N = 100 · 2.",
    )


# =========================================================================== A6 DSO
@demo(
    "I-24",
    "A6",
    "The DSO balance ignores Stage-3 DSO trades",
    "|B_DSO| after the DSO buys 10 kWh (eq. 7)",
)
def i24():
    m, _, dso, _ = matcher()
    m.match_orders(0, [order("a1", 50.0, 10.0, False)], {}, 0.0)
    return (
        10.0,
        abs(dso.balance),
        "The balance only moves for Stage-1 DSO-preferred orders, so it stays 0 by "
        "default (T4).",
    )


@demo(
    "I-28",
    "A6",
    "Grid fees are never charged",
    "DSO profit includes the fees it computed",
)
def i28():
    m, _, dso, locs = matcher(located=True)
    res = m.match_orders(
        0,
        [order("a0", 200.0, 10.0, True, locs), order("a1", 50.0, 10.0, False, locs)],
        {},
        0.0,
    )
    fees = sum(t.fees for t in res.trades)
    dso_margin = sum(
        t.quantity * t.price for t in res.trades if t.seller_id == "DSO"
    ) - sum(t.quantity * t.price for t in res.trades if t.buyer_id == "DSO")
    return (
        round(dso_margin + fees, 4),
        round(dso.profit, 4),
        f"Fees of {fees:.2f} are stored on the trade and summed in dso.fees, but "
        "nobody pays them.",
    )


# =========================================================================== A7 grid
@demo(
    "I-32",
    "A7",
    "Stage-2 trades do not load the grid",
    "edge flow added by a 10 kWh P2P trade across the line (> 0)",
)
def i32():
    m, grid, _, locs = matcher(located=True)
    before = sum(grid.edge_flows.values())
    m.match_orders(
        0,
        [order("a0", 200.0, 10.0, True, locs), order("a1", 50.0, 10.0, False, locs)],
        {},
        0.0,
    )
    return "> 0", "> 0" if sum(grid.edge_flows.values()) - before > 1e-9 else "0.0"


@demo(
    "I-33",
    "A7",
    "The grid starts every episode already loaded",
    "mean congestion before any trade (flows are per period)",
)
def i33():
    grid = GridNetwork(GridTopology.MESH, 3, 300.0, seed=1)
    cong = []
    env = make_env()
    run_episode(env, on_step=lambda e, _: cong.append(round(e.dso.congestion_level, 4)))
    return (
        0.0,
        round(grid.calculate_congestion_level(), 4),
        "Flows start at U(0, 0.3)·capacity and only accumulate; congestion never "
        "decreases within an episode (T10).",
        {"congestion_per_step": cong},
    )


@demo("I-57", "A7", "The IEEE-34 feeder is disconnected", "IEEE-34 graph is connected")
def i57():
    import networkx as nx

    g = GridNetwork(GridTopology.IEEE34, capacity=1800.0, seed=1).graph
    islands = [sorted(c) for c in nx.connected_components(g) if len(c) < 5]
    return True, nx.is_connected(g), f"Island: {islands} (edge 832–888 is missing)."


@demo(
    "I-70",
    "A7",
    "Losses can exceed the energy sent",
    "loss of a 10 kWh transfer over distance 40 ≤ 10",
)
def i70():
    grid = GridNetwork(GridTopology.MESH, 3, 300.0, seed=1)
    loss = grid.transmission_loss(40.0, 10.0)
    return (
        "≤ 10",
        "≤ 10" if loss <= 10 else f"{loss:.1f}",
        "Loss = d · q · 0.03 is linear and unbounded once d · κ > 1.",
    )


# ======================================================================== A8 settlement
@demo(
    "I-18",
    "A8",
    "Selling energy charges the battery",
    "battery level after selling 10 kWh with G = D (start 50, η = 1)",
)
def i18():
    bat = Battery(100, 0.0, 1.0, 1.0, 1.0)
    bat.energy_level = 50.0
    ag = DERAgent(
        "t", 50.0, battery=bat, generation_profile=[20.0], demand_profile=[20.0]
    )
    ag.update_battery_from_trades(0, energy_bought=0.0, energy_sold=10.0)
    return (
        40.0,
        ag.battery.energy_level,
        "The trade term enters with the wrong sign (T7).",
    )


@demo(
    "I-19",
    "A8",
    "A charge that would fill the battery is refused",
    "energy level after charging 10 kWh at 95 of 100 kWh (partial fill to 100)",
)
def i19():
    bat = Battery(100, 0.0, 1.0, 1.0, 1.0)
    bat.energy_level = 95.0
    bat.charge(10.0)
    return 100.0, bat.energy_level


@demo(
    "I-20",
    "A8",
    "Discharge efficiency points the wrong way",
    "stored energy after delivering 9 kWh with η = 0.9 from 50 (eq. 16: E − E_out/η "
    "= 40)",
)
def i20():
    bat = Battery(100, 0.0, 1.0, 1.0, 0.9)
    bat.energy_level = 50.0
    bat.discharge(9.0)
    return (
        40.0,
        round(bat.energy_level, 4),
        "Storage drops by E_out·η, so discharging creates energy.",
    )


@demo(
    "I-21",
    "A8",
    "Demand served from the battery is not counted",
    "demand satisfied when G = 10, D = 20 and the battery covers the other 10",
)
def i21():
    bat = Battery(100, 0.0, 1.0, 1.0, 1.0)
    bat.energy_level = 50.0
    ag = DERAgent(
        "w", 60.0, battery=bat, generation_profile=[10.0], demand_profile=[20.0]
    )
    ag.update_battery_from_trades(0, 0.0, 0.0)  # discharges 10
    ag.update_energy_tracking(0, 0.0, 0.0)
    return (
        20.0,
        ag.cumulative_demand_satisfied,
        f"Battery went 50 → {bat.energy_level:.0f}; the 10 kWh is recorded as "
        "deferred demand.",
    )


@demo(
    "I-23",
    "A8",
    "The grid balance signal is not eq. 20",
    "grid balance = Σ_i (G − D + bought − sold) for the step",
)
def i23():
    env = make_env()
    env.reset(seed=7)
    for i, aid in enumerate(env.agents_id):
        env.action_spaces[aid].seed(i)
    step = env.current_step
    _, _, _, _, info = env.step(
        {aid: env.action_spaces[aid].sample() for aid in env.agents_id}
    )
    trades = info["a0"]["trades"]
    b_grid = sum(
        a.get_generation(step)
        - a.get_demand(step)
        + sum(t.quantity for t in trades if t.buyer_id == a.id)
        - sum(t.quantity for t in trades if t.seller_id == a.id)
        for a in env._agents.values()
    )
    return (
        round(b_grid, 3),
        round(info["a0"]["grid_balance"], 3),
        "The observation and info use dso.balance, which stays 0 (I-24).",
    )


@demo(
    "I-26",
    "A8",
    "The agent balance is not eq. 13",
    "agent balance = (G − D) + (bought − sold)",
)
def i26():
    env = make_env()
    env.reset(seed=7)
    for i, aid in enumerate(env.agents_id):
        env.action_spaces[aid].seed(i)
    step = env.current_step
    _, _, _, _, info = env.step(
        {aid: env.action_spaces[aid].sample() for aid in env.agents_id}
    )
    a = env._agents["a0"]
    trades = info["a0"]["trades"]
    bought = sum(t.quantity for t in trades if t.buyer_id == "a0")
    sold = sum(t.quantity for t in trades if t.seller_id == "a0")
    return (
        round(a.get_generation(step) - a.get_demand(step) + bought - sold, 3),
        round(a.balance, 3),
        "The code stores sold − bought: no G, no D, opposite sign.",
    )


@demo(
    "I-27",
    "A8",
    "Profit is never updated",
    "Σ over the episode of |profit change| for agent a0 (it trades every step)",
)
def i27():
    env = make_env()
    profits, cash = [], []

    def track(e, out):
        a0 = e._agents["a0"]
        profits.append(a0.profit)
        info = out[4]["a0"]
        cash.append(
            sum(
                t.price * t.quantity * (1 if t.seller_id == "a0" else -1)
                for t in info["trades"]
                if "a0" in (t.buyer_id, t.seller_id)
            )
        )

    run_episode(env, on_step=track)
    return (
        round(sum(abs(c) for c in cash), 2),
        round(sum(abs(p) for p in profits), 2),
        "The observation 'mean profit' is therefore always 0 (T5).",
    )


# ============================================================ A9 reputation, A10 ledger
@demo(
    "I-07",
    "A9",
    "All agents start with the same reputation",
    "distinct initial reputations among 3 agents",
)
def i07():
    env = make_env()
    env.reset(seed=7)
    reps = [round(a.reputation, 6) for a in env._agents.values()]
    return 3, len(set(reps)), f"Reputations: {reps}"


@demo(
    "I-38",
    "A9",
    "Nothing is ever unmatched, so reliability is always 1",
    "orders the P2P market could not match (a lone seller)",
)
def i38():
    m, *_ = matcher()
    res = m.match_orders(0, [order("a1", 50.0, 10.0, False)], {}, 0.0)
    return (
        1,
        len(res.unmatched_orders),
        "The DSO fills every residual and unmatched_orders is hard-coded to [].",
    )


@demo(
    "I-66",
    "A10",
    "Tampering with a fee does not break the chain",
    "verify_chain() after changing a recorded trade's fee",
)
def i66():
    v = Validator(difficulty=1)
    t = Trade("a0", "a1", 100.0, 10.0, 0.0, 1.0, 0.3, 5.0)
    v.add_trade(t)
    v._create_new_block()
    t.fees = 500.0
    t.transmission_loss = 9.0
    return (
        False,
        v.verify_chain(),
        "The block hash covers price and quantity but not loss or fees.",
    )


# =========================================================================== B1 KPIs
@demo(
    "I-35",
    "B1",
    "A perfectly balanced trade counts as imbalance",
    "supply-demand imbalance of one 10 kWh buy matched with one 10 kWh sell",
)
def i35():
    ic = ImplicitCooperation(100.0)
    k = ic._get_grid_stability_metrics(0.0, [Trade("a0", "a1", 100.0, 10.0, 0.0)])
    return (
        0.0,
        k["supply_demand_imbalance"],
        "The code divides traded volume by capacity; the coordination score (1 − "
        "imbalance) inherits it.",
    )


@demo(
    "I-36",
    "B1",
    "'Social welfare' is turnover",
    "surplus of a trade with bid 200, ask 50, 10 kWh = (200 − 50) · 10",
)
def i36():
    ic = ImplicitCooperation(100.0)
    k = ic._get_economic_efficiency_metrics(
        [], [Trade("a0", "a1", 125.0, 10.0, 0.0)], SimpleNamespace(history=[])
    )
    return (
        1500.0,
        k["social_welfare"],
        "The code matches the printed formula Σ p·q; the paper's label says surplus. "
        "A decision, not a bug.",
    )


@demo(
    "I-37",
    "B1",
    "Price volatility uses the whole episode",
    "volatility over the last 3 periods (prices 100 × 10, then 200 × 3)",
)
def i37():
    hist = SimpleNamespace(
        history=[SimpleNamespace(clearing_price=p) for p in [100.0] * 10 + [200.0] * 3]
    )
    k = ImplicitCooperation(100.0)._get_economic_efficiency_metrics([], [], hist)
    return (
        0.0,
        round(float(k["price_volatility"]), 3),
        "The paper says 'over a window' without a length; 3 is used here for "
        "illustration.",
    )


# ======================================================================= C1 observation
@demo(
    "I-39",
    "C1",
    "'Forecasts' are the true future",
    "largest forecast error in the observed generation over an episode (max_error = "
    "0.3)",
)
def i39():
    env = make_env(max_error=0.3)
    errs = []

    def track(e, out):
        if e.current_step < e.max_steps:
            a0 = e._agents["a0"]
            errs.append(abs(out[0]["a0"][16] - a0.get_generation(e.current_step)))

    run_episode(env, on_step=track)
    return (
        "> 0",
        "> 0" if max(errs) > 1e-6 else f"{max(errs):.1f}",
        "Remaining demand and supply are exact sums of the future profile as well.",
    )


@demo(
    "I-40",
    "C1",
    "Observations are not normalised",
    "largest |observation| over an episode, if normalised (decision)",
)
def i40():
    env = make_env()
    top = []
    run_episode(
        env, on_step=lambda e, out: top.append(float(np.max(np.abs(out[0]["a0"]))))
    )
    return (
        "≤ 1",
        "≤ 1" if max(top) <= 1 else f"{max(top):.0f}",
        "The paper does not say whether observations are scaled; a decision.",
    )


@demo(
    "I-58",
    "C1",
    "The reset observation hides the first period",
    "demand in the reset observation = D at t = 0",
)
def i58():
    env = make_env()
    obs, _ = env.reset(seed=7)
    return (
        round(env._agents["a0"].get_demand(0), 3),
        round(float(obs["a0"][17]), 3),
        "The agent chooses its first action without seeing its own generation, "
        "demand or the KPIs.",
    )


# =========================================================================== C2 reward
def _episode_kpis():
    env = make_env()
    last = {}
    run_episode(env, on_step=lambda e, out: last.update(info=out[4]["a0"]))
    info = last["info"]
    k = env.implicit_cooperation.get_kpis(
        env.current_step - 1,
        "DSO",
        [*env._agents.values()],
        info["orders"],
        info["trades"],
        env.dso.congestion_level,
        env.market.matching_history,
    )
    return env, k


@demo(
    "I-41",
    "C2",
    "f_coop is far outside [0, 1]",
    "f_coop at the last step lies in [0, 1]",
)
def i41():
    env, k = _episode_kpis()
    h = env.reward_handler
    inv = dict(k)
    for m in [
        "supply_demand_imbalance",
        "grid_congestion",
        "price_volatility",
        "avg_bid_ask_spread",
    ]:
        inv[m] = 1.0 - float(inv[m])
    w = dict(
        social_welfare=h.f_social_welfare,
        market_liquidity=h.f_market_liquidity,
        avg_bid_ask_spread=h.f_avg_bid_ask_spread,
        price_volatility=h.f_price_volatility,
        supply_demand_imbalance=h.f_supply_demand_imbalance,
        grid_congestion=h.f_grid_congestion,
        coordination_score=h.f_coordination_score,
        coordination_convergence=h.f_coordination_convergence,
        der_self_consumption=h.f_der_self_consumption,
        flexibility_utilization=h.f_flexibility_utilization,
    )
    f_coop = sum(w[m] * inv[m] for m in w) / sum(w.values())
    return (
        "in [0, 1]",
        "in [0, 1]" if 0 <= f_coop <= 1 else f"{f_coop:.0f}",
        "Social welfare and liquidity enter unnormalised (T9).",
        {"kpis": {kk: round(float(v), 3) for kk, v in k.items()}},
    )


@demo(
    "I-42",
    "C2",
    "Three different cooperation boosts",
    "one definition of the boost factor for f_coop · f_contrib = 0.5",
)
def i42():
    x = 0.5
    forms = {
        "[P1] eq. 4 as printed": 1 + math.log1p(max(0.0, x - 1)) / 5,
        "code": 1 + math.log1p(x) / 5,
        "[P2] eq. 3": 1 + x,
    }
    return (
        1,
        len({round(v, 6) for v in forms.values()}),
        ", ".join(f"{k}: {v:.3f}" for k, v in forms.items()),
        {"forms": forms},
    )


@demo(
    "I-43",
    "C2",
    "r_res is always −1.5 because the order was overwritten",
    "r_res for an order that was filled completely",
)
def i43():
    m, grid, dso, _ = matcher()
    b = order("a0", 200.0, 10.0, True)
    submitted = copy.copy(b)
    res = m.match_orders(0, [b, order("a1", 50.0, 10.0, False)], {}, 0.0)
    h = RewardHandler(dso, grid)
    trades = [t for t in res.trades if "a0" in (t.buyer_id, t.seller_id)]
    return (
        h._calculate_resource_allocation_reward(submitted, trades),
        h._calculate_resource_allocation_reward(b, trades),
        "The reward receives the mutated order (quantity 0) from I-12; r_trade is 0 "
        "for the same reason.",
    )


@demo(
    "I-45",
    "C2",
    "The local-trade weight is overwritten",
    "weight of local trades in r_trade (the 'Trade weights' block sets 0.7)",
)
def i45():
    m, grid, dso, _ = matcher()
    return (
        0.7,
        RewardHandler(dso, grid)._w_local,
        "_w_local is set again to 0.3 in the 'Contribution weights' block.",
    )


@demo(
    "I-47",
    "C2",
    "Every agent without trades gets the same fixed reward",
    "rewards of two different agents without trades differ",
)
def i47():
    m, grid, dso, _ = matcher()
    res = m.match_orders(
        0, [order("a0", 200.0, 10.0, True), order("a1", 50.0, 10.0, False)], {}, 0.0
    )
    h = RewardHandler(dso, grid)
    rich = DERAgent("x", 60.0, generation_profile=[50.0], demand_profile=[0.1])
    poor = DERAgent("y", 60.0, generation_profile=[0.1], demand_profile=[50.0])
    r = [
        round(
            float(
                h.calculate_reward(
                    a, order(a.id, 100.0, 5.0, True), res, {}, 10.0, 300.0
                )
            ),
            3,
        )
        for a in (rich, poor)
    ]
    return (
        "different",
        "different" if r[0] != r[1] else f"both {r[0]}",
        "Fixed −20·ln(1 + 5/20) before any other term; reachable when q_min = 0 "
        "(Case 6).",
    )


# ========================================================================== D1 training
def _grouped_env_config():
    ids, caps = ["b", "a"], [30.0, 90.0]
    agents = [
        DERAgent(i, c, generation_profile=[10.0] * 24, demand_profile=[20.0] * 24)
        for i, c in zip(ids, caps)
    ]
    return {
        "max_steps": 24,
        "market_config": market_config(),
        "agents": agents,
        "grid_network": GridNetwork(GridTopology.MESH, 2, 300.0, seed=1),
        "seed": 7,
    }


@demo(
    "I-59",
    "D1",
    "Grouped spaces are sorted, grouped data is not",
    "the space in tuple slot 0 belongs to the agent in slot 0 ('b', q_max 30)",
)
def i59():
    from src_thesis.marl.train import GroupedLEM

    g = GroupedLEM(_grouped_env_config())
    slot0_qmax = float(g.action_space["grouped_agents"][0].high[1])
    owner = "b" if slot0_qmax == 30.0 else "a"
    return (
        "b",
        owner,
        f"Group order {g.original_agents_id}; tuple spaces follow sorted keys ['a', "
        "'b'].",
    )


@demo(
    "I-62",
    "D1",
    "A positive evaluation_duration is rejected",
    "RLTrainer(..., evaluation_duration=5) is accepted",
)
def i62():
    from src_thesis.marl.train import RLTrainer

    try:
        RLTrainer(_grouped_env_config(), evaluation_duration=5, iters=10)
        return "accepted", "accepted"
    except ValueError as e:
        return "accepted", "ValueError", str(e)


# -------------------------------------------------------------- showability of the rest
SHOWABILITY: dict[str, tuple[str, str]] = {
    # tier "inspect": a constant, a default or a formula; reading one line shows it
    "I-06": (
        "inspect",
        "Profile generation form and CSV column choice; shown by reading the generator",
    ),
    "I-22": (
        "inspect",
        "No conservation identity exists; a demo can print the per-agent residual "
        "once one is decided",
    ),
    "I-25": ("inspect", "Two opposite sign conventions side by side in matching.py"),
    "I-29": ("inspect", "F_trans is the literal 0.0"),
    "I-30": ("inspect", "Caps 0.2 / 0.3 are literals"),
    "I-31": (
        "inspect",
        "Follows from P2P impact 0 and DSO trades carrying no fees (I-54)",
    ),
    "I-34": ("inspect", "κ = 0.03 is a default argument"),
    "I-44": ("inspect", "Follows from I-24: every term multiplied by dso.balance is 0"),
    "I-46": ("inspect", "p_dso vs p_no_trades in the penalty formula"),
    "I-49": ("inspect", "PBT mutation domains are literals in train.py"),
    "I-50": (
        "inspect",
        "`iters` is passed as RLlib's training_iteration stop criterion",
    ),
    "I-52": (
        "inspect",
        "`pytest -q` itself: 3 failures and 17 errors on the original tests",
    ),
    "I-53": ("inspect", "Bare except / clamped capacity; shown by reading"),
    "I-56": ("inspect", "Unit strings in docstrings and defaults"),
    "I-63": (
        "inspect",
        "Round trip of EnvConfigHandler; feasible demo, not yet written",
    ),
    "I-71": ("inspect", "No power-limit parameter exists on Battery"),
    "I-74": ("inspect", "Threshold literals 0.2 < 0.8"),
    "I-79": ("inspect", "Heuristic formula vs [P2]'s derivative"),
    # tier "harness": needs a training or inference run
    "I-48": (
        "harness",
        "Needs one RLlib update of the CTDE module to show pi_heads keep their "
        "initial weights",
    ),
    "I-60": ("harness", "Comparing CTCE to the others needs trained policies"),
    "I-61": (
        "harness",
        "Needs a checkpoint to compare standalone inference with RLlib's action path",
    ),
    "I-64": ("harness", "About the experiment pipeline (manifests, baselines, seeds)"),
    "I-72": ("harness", "About the evaluation protocol of a training run"),
    "I-73": ("harness", "Return scale per paradigm; visible in training curves"),
    # tier "judgment": a paper or documentation question with nothing to execute
    "I-51": ("judgment", "The profile-to-agent mapping is unpublished"),
    "I-65": ("judgment", "Unaudited analytics module"),
    "I-67": ("judgment", "Documentation describes a different repository state"),
    "I-68": ("judgment", "Definition of imbalance (orders vs trades vs physical)"),
    "I-69": ("judgment", "Label vs quantity"),
    "I-75": ("judgment", "Missing normalisation ranges in the paper"),
    "I-76": ("judgment", "Missing R_base formulas in the paper"),
    "I-80": ("judgment", "B_index is undefined in the paper"),
}


def showability() -> dict[str, tuple[str, str]]:
    """Tier and reason for every issue I-01 … I-80 ("demo" for those in REGISTRY)."""
    out = {k: ("demo", REGISTRY[k].title) for k in REGISTRY}
    out.update({k: v for k, v in SHOWABILITY.items() if k not in out})
    return dict(sorted(out.items()))


if __name__ == "__main__":
    for d in run_all():
        mark = "REPRODUCED" if d.reproduced else "not reproduced"
        print(
            f"{d.issue} [{d.step}] {mark:14} {d.title}\n    expected: {d.expected}\n  "
            f"  actual:   {d.actual}"
        )
