"""Evidence T1-T13 for docs/thesis/validation/issues.md.

Runs the ORIGINAL MARLEM code (marlem-dev/src, byte-identical to marlem-main/src)
for one episode with random actions and prints the facts the outline cites (T1-T11).

Run from anywhere with the `marlem` conda env:
    python docs/thesis/validation/evidence/trace_original_episode.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
import numpy as np
from src.agent.der import DERAgent
from src.agent.battery import Battery
from src.grid.base import GridTopology
from src.grid.network import GridNetwork
from src.market.matching import MarketConfig
from src.market.mechanism import ClearingMechanism
from src.market.mechanism import SellerPricing, BuyerPricing
from src.market.order import Order
from src.environment.lem import LocalEnergyMarket
import src.environment.reward as R

# --- instrument reward to see the order quantity it receives
seen = []
orig = R.RewardHandler.calculate_reward


def spy(self, agent, order, matching, kpis, mn, mx, is_terminal=False):

    r = orig(self, agent, order, matching, kpis, mn, mx, is_terminal)

    seen.append(
        dict(
            agent=agent.id,
            order_q_at_reward=order.quantity,
            is_terminal=is_terminal,
            reward=float(r),
            n_trades=sum(
                1 for t in matching.trades if agent.id in (t.buyer_id, t.seller_id)
            ),
        )
    )
    return r


R.RewardHandler.calculate_reward = spy

mc = MarketConfig(
    min_price=10.0,
    max_price=300.0,
    min_quantity=0.1,
    max_quantity=100.0,
    price_mechanism=ClearingMechanism.AVERAGE,
    blockchain_difficulty=1,
)
G = [10.0] * 24
Dm = [20.0] * 24
agents = [
    DERAgent(
        "a0",
        60.0,
        battery=Battery(50, 0.1, 0.9, 0.95, 0.95),
        generation_profile=G,
        demand_profile=Dm,
    ),
    DERAgent("a1", 60.0, generation_profile=G, demand_profile=Dm),
    DERAgent("a2", 60.0, generation_profile=G, demand_profile=Dm),
]
grid = GridNetwork(GridTopology.MESH, 3, 300.0, seed=1)
env = LocalEnergyMarket(
    {
        "max_steps": 24,
        "market_config": mc,
        "agents": agents,
        "grid_network": grid,
        "seed": 7,
    }
)
obs, _ = env.reset(seed=7)
print(
    "configured flat profiles kept after reset:", env._agents["a0"].demand_profile == Dm
)

for i, aid in enumerate(env.agents_id):
    env.action_spaces[aid].seed(i)  # reproducible random actions
steps, balances, profits = 0, [], []
done = False
while not done:
    acts = {aid: env.action_spaces[aid].sample() for aid in env.agents_id}
    obs, rew, term, trunc, info = env.step(acts)
    steps += 1
    balances.append(env.dso.balance)
    profits.append([a.profit for a in env._agents.values()])
    done = term["__all__"]

print("steps executed per episode:", steps, "(max_steps=24)")
print("any is_terminal=True seen by reward:", any(s["is_terminal"] for s in seen))
print(
    "order.quantity at reward time (max over all):",
    max(s["order_q_at_reward"] for s in seen),
)
print("distinct dso.balance values:", sorted(set(round(b, 6) for b in balances))[:5])
print("agent profit ever non-zero:", any(any(p) for p in profits))
print(
    "no-trade reward value:",
    sorted(set(round(s["reward"], 4) for s in seen if s["n_trades"] == 0)),
)

# --- f_coop range check with the KPIs of the last step
k = env.implicit_cooperation.get_kpis(
    env.current_step - 1,
    "DSO",
    [*env._agents.values()],
    info["a0"]["orders"],
    info["a0"]["trades"],
    env.dso.congestion_level,
    env.market.matching_history,
)
print("KPIs last step:", {kk: round(float(v), 3) for kk, v in k.items()})

# --- pricing mechanism: SELLER should return the sell price
b = Order("b", "x", 200.0, 1.0, True, 0.0)
s = Order("s", "y", 50.0, 1.0, False, 0.0)
print(
    "SELLER pricing(buy=200, sell=50) ->",
    ClearingMechanism.SELLER.get_instance().calculate_price(b, s, 100.0),
)

# --- battery sign: agent sells 10 with G=D -> household must discharge, code charges?
from src.agent.der import DERAgent as D

bat = Battery(100, 0.0, 1.0, 1.0, 1.0)
bat.energy_level = 50.0
ag = D("t", 50.0, battery=bat, generation_profile=[20.0], demand_profile=[20.0])
ag.update_battery_from_trades(0, energy_bought=0.0, energy_sold=10.0)
print("battery after selling 10 kWh with G=D (start 50):", ag.battery.energy_level)

# --- is_buy inconsistency: raw 0.3 -> adjust() treats as buy, env treats as sell
ag2 = D("u", 50.0, generation_profile=[5.0], demand_profile=[30.0])
adj = ag2.adjust_action_for_battery(0, np.array([100.0, 40.0, 0.3, 0.0]), mc)
print(
    "adjust(q=40, is_buy=0.3, G=5, D=30) ->",
    adj,
    "; env order is_buy =",
    bool(adj[2] > 0.5),
)

# --- f_coop as computed in RewardHandler.calculate_reward (paper: "normalized to [0,1]")
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
print(
    "f_coop (last step):",
    round(sum(w[m] * inv[m] for m in w) / sum(w.values()), 2),
    "; total weight:",
    sum(w.values()),
)

# --- congestion over a fresh episode: does edge flow ever go down between steps?
env.reset(seed=7)
cong = []
for _ in range(23):
    _, _, term, _, _ = env.step(
        {aid: env.action_spaces[aid].sample() for aid in env.agents_id}
    )
    cong.append(round(env.dso.congestion_level, 4))
    if term["__all__"]:
        break
print("congestion per step:", cong)
print(
    "congestion ever decreases within episode:",
    any(b < a for a, b in zip(cong, cong[1:])),
)

# --- T12: BID_ASK_SPREAD receives market_price as its `factor` argument (clipped to [0,1])
print(
    "BID_ASK_SPREAD pricing(buy=200, sell=50, market=100) ->",
    ClearingMechanism.BID_ASK_SPREAD.get_instance().calculate_price(b, s, 100.0),
)

# --- T13: IEEE34 graph connectivity (edge 832-888 missing)
import networkx as nx

g34 = GridNetwork(GridTopology.IEEE34, capacity=1800.0, seed=1).graph
print(
    "IEEE34 connected:",
    nx.is_connected(g34),
    "; small islands:",
    [sorted(c) for c in nx.connected_components(g34) if len(c) < 5],
)
