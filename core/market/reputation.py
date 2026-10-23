"""Reputation system for tracking agent behavior in the Local Energy Market.

This module implements a decentralized reputation system that evaluates agent
reliability, price fairness, and grid contribution based on market outcomes
([P1] §3.3.4, eq. 12): r_i = w_rel·δ_rel + w_fair·δ_fair + w_grid·δ_grid.

The original's ``ReputationHandler``, kept as it was, with every reputation dial
here (the weights and the decay). It now reads a step's ``StepRecord`` instead of
the original's ``MatchingResult``. Where the original disagreed with [P1] it is
changed, each marked "[P1]" below:

    decay        a constant factor (the original blended by the time of day, so
                 late in the day new behaviour counted almost nothing)
    reliability  matched to total order VOLUME, matched by peers (the original
                 counted trades against unmatched orders, which the DSO always
                 clears, so it was always 1)
    fairness     the agent's peer trades against the step's peer clearing price
                 (the original's clearing price included the DSO's trades)
    grid         on the market's balance B_grid of the step (the original's
                 balance stayed 0, so this part was always neutral); a trade with
                 the DSO is neutral, 0 on the -1 to 1 scale (the original returned
                 0.5 there)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Tuple

import numpy as np

from .order import Trade

if TYPE_CHECKING:
    from .agent.der import Participant as DERAgent
    from .lem import StepRecord


@dataclass(frozen=True)
class ReputationScore:
    """One agent's reputation update for one step: the three components of [P1]
    eq. 12, their weighted sum, and the reputation after the decay blend.

    Not in the original (it returned only the new reputation); kept so the
    notebook can show why a reputation moved.
    """

    reliability: float
    fairness: float
    grid: float
    score: float
    reputation: float


class ReputationHandler:
    """Manages agent reputation in the Local Energy Market.

    This system calculates reputation scores based on market matching results,
    evaluating agents on reliability, price fairness, and grid contribution.
    """

    def __init__(
        self,
        reliability_weight: float = 0.3,
        fairness_weight: float = 0.2,
        grid_weight: float = 0.5,
        decay: float = 0.8,
    ) -> None:
        """Initialize the reputation system.

        Args:
            reliability_weight: w_rel in [P1] eq. 12 (the paper gives no value)
            fairness_weight: w_fair in [P1] eq. 12 (the paper gives no value)
            grid_weight: w_grid in [P1] eq. 12 (the paper gives no value)
            decay: Share of the old reputation kept at each update, the decay
                factor of [P1] §3.3.4 (the paper gives no value)
        """
        self.reliability_weight = reliability_weight
        self.fairness_weight = fairness_weight
        self.grid_weight = grid_weight
        self.decay = decay
        self._neutral = 0.5

        # Check initialization
        self._check_init()

    def _check_init(self) -> None:
        """Check if the reputation handler is initialized correctly."""
        for name in ("reliability_weight", "fairness_weight", "grid_weight", "decay"):
            value = getattr(self, name)
            if value < 0.0 or value > 1.0:
                raise ValueError(
                    f"{name} must be between 0.0 and 1.0. Current value: "
                    f"<{name} = {value}>."
                )

        total = self.reliability_weight + self.fairness_weight + self.grid_weight

        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                "Weights must sum to 1.0. Current value: "
                f"<reliability_weight = {self.reliability_weight}, "
                f"fairness_weight = {self.fairness_weight}, "
                f"grid_weight = {self.grid_weight}>."
            )

    def reset(self, seed: Optional[int] = None) -> float:
        """Generate initial reputation score for an agent (random; not in [P1]).

        Not used by ``LocalEnergyMarket``, which starts every agent at 0.5.

        Args:
            seed: Optional random seed for reproducible reputation initialization

        Returns:
            Initial reputation score between 0.0 and 1.0
        """
        return float(np.random.default_rng(seed).uniform(0.0, 1.0))

    def update_reputation(
        self, agent: DERAgent, record: StepRecord, dso_id: str = "DSO"
    ) -> ReputationScore:
        """Update reputation metrics for an agent based on the step's outcome.

        [P1] §3.3.4: the new score is blended into the old reputation with the
        decay factor, so recent behaviour weighs more and the past fades:
        r ← decay · r + (1 − decay) · score.

        Args:
            agent: DERAgent object
            record: The step's record (orders, trades, clearing price, balance)
            dso_id: ID of the DSO agent for identifying DSO trades

        Returns:
            The step's components, score and updated reputation
        """
        reliability, fairness, grid, new_reputation = self._calculate_reputation(
            agent, record, dso_id
        )
        reputation = (self.decay * agent.reputation) + (
            (1.0 - self.decay) * new_reputation
        )

        return ReputationScore(reliability, fairness, grid, new_reputation, reputation)

    def get_agent_ranking(self, agents: List[DERAgent]) -> List[Tuple[str, float]]:
        """Get ranked list of agents by overall reputation.

        Args:
            agents: List of DERAgent objects to rank

        Returns:
            List of (agent_id, score) tuples, sorted by score (highest first)
        """
        rankings = [(agent.id, agent.reputation) for agent in agents]
        return sorted(rankings, key=lambda x: x[1], reverse=True)

    def _calculate_reputation(
        self, agent: DERAgent, record: StepRecord, dso_id: str
    ) -> Tuple[float, float, float, float]:
        """Calculate reputation metrics for an agent based on the step's outcome.

        This method calculates reputation considering three key components:
        1. Reliability - How much of the agent's order did peers match?
        2. Price fairness - How close were the agent's prices to the market clearing price?
        3. Grid contribution - Did the agent's trades help balance the grid?

        Args:
            agent: DERAgent object
            record: The step's record
            dso_id: ID of the DSO agent for identifying DSO trades

        Returns:
            (reliability, fairness, grid contribution, calculated score [0-1])
        """
        # If there are no trades in the step, the existing reputation stands
        if not record.trades:
            return (
                self._neutral,
                self._neutral,
                self._neutral,
                agent.reputation,
            )

        agent_trades = [
            t
            for t in record.trades
            if t.buyer_id == agent.id or t.seller_id == agent.id
        ]
        agent_orders = [o for o in record.orders if o.agent_id == agent.id]
        p2p_trades = [
            t for t in agent_trades if dso_id not in (t.buyer_id, t.seller_id)
        ]

        # STEP 1. Reliability score: δ_rel ([P1] eq. 12): matched to total order
        # volume. [P1]: by volume, and matched by peers, since the DSO clears all.
        ordered = sum(o.quantity for o in agent_orders)
        matched = sum(t.quantity for t in p2p_trades)
        reliability = min(1.0, matched / ordered) if ordered > 0 else self._neutral

        # STEP 2. Price fairness: δ_fair ([P1] eq. 12): deviation from the market
        # clearing price. [P1]: the agent's peer trades, as the clearing price is
        # the peer trades' (the DSO's tariffs would count as unfair prices).
        clearing_price = record.clearing_price

        if p2p_trades and clearing_price > 0:
            price_deviations = [
                abs(t.price - clearing_price) / clearing_price for t in p2p_trades
            ]
            fairness = 1.0 - min(1.0, float(np.mean(price_deviations)))
        else:
            fairness = self._neutral

        # STEP 3. Grid contribution: δ_grid ([P1] eq. 12)
        if agent_trades:
            grid_contributions = []

            for trade in agent_trades:
                # Calculate the impact of this trade on grid stability
                impact = self._calculate_grid_impact(
                    agent.id, trade, record.grid_balance_kwh, dso_id
                )
                grid_contributions.append(impact)

            # Average the contributions across all trades
            grid_contribution = float(np.mean(grid_contributions))

            # Normalize to 0-1 range (since _calculate_grid_impact returns -1 to 1)
            grid_contribution = (grid_contribution + 1) / 2
        else:
            grid_contribution = self._neutral

        # Calculate overall score with weights ([P1] eq. 12)
        overall_score = (
            (self.reliability_weight * reliability)
            + (self.fairness_weight * fairness)
            + (self.grid_weight * grid_contribution)
        )

        return (
            reliability,
            fairness,
            grid_contribution,
            max(0.0, min(1.0, overall_score)),
        )

    def _calculate_grid_impact(
        self, agent_id: str, trade: Trade, grid_balance: float, dso_id: str
    ) -> float:
        """Calculate trade's impact on grid stability (the min(q / |B|, 1) form of
        B_impact, [P1] eq. 8h, on the market's balance B_grid, [P1] eq. 20).

        This method evaluates how a trade impacts grid stability based on the current grid state.
        - Positive impact: Agent helps balance the grid (sells during shortage, buys during excess)
        - Negative impact: Agent worsens grid imbalance (buys during shortage, sells during excess)

        Args:
            agent_id: ID of the DERAgent whose reputation is being calculated
            trade: Completed trade
            grid_balance: The step's balance B_grid (positive = excess supply,
                negative = shortage), kWh
            dso_id: ID of the DSO agent for identifying DSO trades

        Returns:
            Impact score between -1 and 1 (higher is better for grid stability)
        """
        impact = 0.0

        # If grid is balanced, neutral impact
        if abs(grid_balance) < 0.1:
            return 0.0

        # For DSO trades, evaluate differently
        if (trade.buyer_id == dso_id) or (trade.seller_id == dso_id):
            # DSO trades are neutral: 0 on this -1 to 1 scale (the original
            # returned 0.5 here, which counted them as helping)
            return 0.0

        # Calculate impact based on grid state and agent's role
        is_buyer = trade.buyer_id == agent_id

        if grid_balance > 0:  # Excess supply
            if is_buyer:
                # Buying during excess is good (+)
                impact = min(1.0, trade.quantity / abs(grid_balance))
            else:
                # Selling during excess is bad (-)
                impact = -min(1.0, trade.quantity / abs(grid_balance))
        else:  # grid_balance < 0, Shortage
            if is_buyer:
                # Buying during shortage is bad (-)
                impact = -min(1.0, trade.quantity / abs(grid_balance))
            else:
                # Selling during shortage is good (+)
                impact = min(1.0, trade.quantity / abs(grid_balance))

        return impact
