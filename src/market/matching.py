"""
Order matching implementation for the Local Energy Market.

This module handles the matching of buy and sell orders in a decentralized manner,
considering grid constraints and market rules.
"""

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..grid.network import GridNetwork
from .dso import DSOAgent
from .mechanism import ClearingMechanism
from .order import Order, Trade
from .validation import Validator


# region Market data structures and matching
@dataclass
class MarketConfig:
    """Market configuration parameters.

    This class defines the configuration parameters for the local energy market (LEM).
    It includes settings for market rules, pricing mechanisms, grid constraints,
    DSO interaction, and preference-based matching.

    Preference-based matching allows agents to express preferences for specific trading partners,
    enabling the study of emergent trading relationships and decentralized coordination
    in multi-agent systems with limited information sharing.
    """

    # region Market configuration
    min_price: float = 0.0  # Minimum allowed price ($/Wh)
    max_price: float = 1000.0  #  Maximum allowed price($/Wh)
    min_quantity: float = 0.0  # Minimum allowed quantity (Wh)
    max_quantity: float = 1000.0  # Maximum allowed quantity (Wh)
    price_mechanism: ClearingMechanism = (
        ClearingMechanism.AVERAGE
    )  # Type of pricing mechanism to use
    blockchain_difficulty: int = (
        2  # 0 disables proof-of-work while retaining the audit chain
    )
    visualize_blockchain: bool = False  # Enable/disable blockchain visualization
    enable_partner_preference: bool = (
        False  # Use RL-based (vs rule-based) partner selection
    )
    _threshold: float = 1e-6  # Minimum quantity threshold for matching orders

    def __post_init__(self) -> None:
        """Validate the market configuration parameters."""
        self._check_init()

    def _check_init(self) -> None:
        """Validate the market configuration parameters."""
        if self.max_price <= self.min_price:
            raise ValueError(
                f"Maximum price must be greater than minimum price, got <max_price = {self.max_price}> and <min_price = {self.min_price}>."
            )

        if self.min_quantity < 0:
            raise ValueError(
                f"Minimum quantity must be positive, got <min_quantity = {self.min_quantity}>."
            )

        if self.max_quantity <= self.min_quantity:
            raise ValueError(
                f"Maximum quantity must be greater than minimum quantity, got <max_quantity = {self.max_quantity}> and <min_quantity = {self.min_quantity}>."
            )

        if (
            not isinstance(self.blockchain_difficulty, int)
            or self.blockchain_difficulty < 0
        ):
            raise ValueError(
                f"Blockchain difficulty must be a non-negative integer, got <blockchain_difficulty = {self.blockchain_difficulty}>."
            )

        if not isinstance(self.price_mechanism, ClearingMechanism):
            raise ValueError(
                f"Unknown pricing mechanism: <price_mechanism = {self.price_mechanism}>. Valid options are: {list(ClearingMechanism)}."
            )

        if self._threshold < 0:
            raise ValueError(
                f"Threshold must be positive, got <_threshold = {self._threshold}>."
            )

    # endregion


@dataclass
class MatchingResult:
    """Result of order matching process."""

    # Matching result
    trades: List[Trade]
    unmatched_orders: List[Order]
    clearing_price: float
    clearing_volume: float

    # Market metrics
    dso_buy_volume: float
    dso_sell_volume: float
    dso_total_volume: float
    p2p_volume: float
    dso_trade_ratio: float
    dso_grid_import: float
    dso_buy_price: float
    dso_sell_price: float
    price_spread: float
    local_price_avg: float
    local_price_advantage: float

    # Grid metrics
    grid_balance: float
    grid_congestion: float
    submitted_orders: List[Order] = field(default_factory=list)
    physical_settlements: Dict = field(default_factory=dict)
    kpis: Dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Convert all numpy numeric types to standard float."""
        for k, v in self.__annotations__.items():
            if v is float:
                setattr(self, k, float(getattr(self, k)))


class MatchingHistory:
    """History of order matching process."""

    def __init__(self):
        """Initialize the matching history."""
        self.history: List[MatchingResult] = []

    def reset(self):
        """Reset the matching history."""
        self.history = []

    def update(self, matching_result: MatchingResult):
        """Update the matching history.

        Args:
            matching_result: Matching result to add to the history
        """
        self.history.append(matching_result)

    def get_matching_result(self, step: int) -> MatchingResult:
        """Get the matching result at a specific step.

        Args:
            step: Step to get the matching result for

        Returns:
            Matching result at the specified step
        """
        return self.history[step]


class OrderMatcher:
    """Matches buy and sell orders while considering grid constraints."""

    # region Matcher lifecycle and validation
    def __init__(
        self,
        num_agents: int,
        config: MarketConfig,
        grid_network: GridNetwork,
        dso_agent: DSOAgent,
    ) -> None:
        """Initialize the order matcher.

        Args:
            num_agents: Number of agents in the market
            config: Market configuration parameters
            grid_network: GridNetwork object representing the network topology
            dso_agent: DSOAgent object representing the DSO agent
        """
        # Store references to the shared scenario components.
        self.num_agents = num_agents
        self.config = config
        self.grid_network = grid_network
        self.dso = dso_agent

        # Validation is optional proof-of-work plus an audit chain.
        self.validator = Validator(self.config.blockchain_difficulty)

        # Keep period history, grid capacity, and cash positions together.
        self.matching_history: MatchingHistory = MatchingHistory()
        self.grid_capacity: float = config.max_quantity * self.num_agents
        self.trades: List[Trade] = []
        self.cash_ledger = {}

        # Check initialization
        self._check_init()

    def reset(self, seed: Optional[int] = None) -> None:
        """Reset the order matcher."""
        if seed is not None:
            np.random.seed(seed)

        # Reset external market state before clearing local history.
        self.dso.reset(seed)

        self.validator.reset()

        self.matching_history.reset()
        self.trades = []
        self.cash_ledger = {}

    def _check_init(self) -> None:
        """Validate the market configuration parameters.

        This method checks for consistency of configuration parameters, especially when
        using time-varying price profiles.

        Raises:
            ValueError: If min_price is greater than or equal to max_price
            ValueError: If min_quantity is non-positive
            ValueError: If max_quantity is less than or equal to min_quantity
            ValueError: If num_agents is non-positive
            ValueError: If grid_network is None
            ValueError: If dso is None
        """
        # Validate num_agents
        if self.num_agents <= 0:
            raise ValueError(
                f"Number of agents must be positive, got {self.num_agents}"
            )

        # Validate grid_network
        if self.grid_network is None:
            raise ValueError("Grid network cannot be None")

        # Validate DSO
        if self.dso is None:
            raise ValueError("DSO agent cannot be None")

        # Validate min/max price relationship
        if self.config.min_price >= self.config.max_price:
            raise ValueError(
                f"Minimum price must be less than maximum price, got <min_price = {self.config.min_price}> and <max_price = {self.config.max_price}>."
            )

        # Validate quantity bounds
        if self.config.min_quantity < 0:
            raise ValueError(
                f"Minimum quantity must be positive, got <min_quantity = {self.config.min_quantity}>."
            )

        if self.config.max_quantity <= self.config.min_quantity:
            raise ValueError(
                f"Maximum quantity must be greater than minimum quantity, got <max_quantity = {self.config.max_quantity}> and <min_quantity = {self.config.min_quantity}>."
            )

        # Check if the pricing mechanism is valid
        if self.config.price_mechanism not in ClearingMechanism:
            raise ValueError(
                f"Unknown pricing mechanism: <price_mechanism = {self.config.price_mechanism}>. Valid options are: {list(ClearingMechanism)}."
            )

        # Validate blockchain difficulty
        if (
            not isinstance(self.config.blockchain_difficulty, int)
            or self.config.blockchain_difficulty < 0
        ):
            raise ValueError(
                f"Blockchain difficulty must be a non-negative integer, got <blockchain_difficulty = {self.config.blockchain_difficulty}>."
            )

    # endregion

    # region Clearing and settlement
    def match_orders(self, current_step, orders, reputation_scores, grid_balance=0.0):
        """Clear preferences, price/reputation/time priority, then bounded fallback.

        Every stage owns residual copies and uses one common feasible fill routine.
        Buy residuals are delivered energy; sell residuals are source energy.
        """
        # Start a fresh physical period and copy submitted orders.
        self.grid_network.begin_period()
        self.dso.balance = grid_balance
        self.dso.prepare_period(current_step)
        remaining = [
            replace(order)
            for order in orders
            if order.quantity > self.config._threshold
        ]
        for order in remaining:
            if (
                not np.isfinite([order.quantity, order.price, order.timestamp]).all()
                or order.quantity < 0
            ):
                raise ValueError(
                    "Order quantities, prices and timestamps must be finite."
                )
        reference = (
            self.matching_history.history[-1].clearing_price
            if self.matching_history.history
            else self.dso.get_market_price(current_step)
        )
        trades = []
        # Stage 1: honor explicit partner preferences.
        if self.config.enable_partner_preference:
            preferred = [o for o in remaining if o.partner_id == self.dso.id]
            fills, _ = self.dso.clear_unmatched_orders(
                current_step,
                [o for o in preferred if o.is_buy],
                [o for o in preferred if not o.is_buy],
            )
            trades.extend(fills)
            for buy in [o for o in remaining if o.is_buy]:
                for sell in [o for o in remaining if not o.is_buy]:
                    if (
                        buy.partner_id == sell.agent_id
                        and sell.partner_id == buy.agent_id
                    ):
                        fill, _ = self._create_trade(buy, sell, grid_balance, reference)
                        if fill is not None:
                            trades.append(fill)
        # Stage 2: match residual orders by price, reputation, and time.
        buys = sorted(
            (o for o in remaining if o.is_buy),
            key=lambda o: (
                -o.price,
                -reputation_scores.get(o.agent_id, 0.0),
                o.timestamp,
                o.id,
            ),
        )
        sells = sorted(
            (o for o in remaining if not o.is_buy),
            key=lambda o: (
                o.price,
                -reputation_scores.get(o.agent_id, 0.0),
                o.timestamp,
                o.id,
            ),
        )
        for buy in buys:
            for sell in sells:
                if buy.quantity <= self.config._threshold:
                    break
                if sell.price > buy.price:
                    break
                fill, _ = self._create_trade(buy, sell, grid_balance, reference)
                if fill is not None:
                    trades.append(fill)
        # Stage 3: route unmatched demand and supply through the DSO.
        fallback, _ = self.dso.clear_unmatched_orders(current_step, buys, sells)
        trades.extend(fallback)
        bought = sum(t.quantity for t in trades if t.buyer_id == self.dso.id)
        sold = sum(t.quantity for t in trades if t.seller_id == self.dso.id)
        stats = self.calculate_market_statistics(
            current_step,
            trades,
            dict(
                dso_buy_volume=bought,
                dso_sell_volume=sold,
                dso_total_volume=bought + sold,
                dso_grid_import=sold - bought,
                dso_profit=self.dso.profit,
            ),
        )
        volume = sum(t.quantity for t in trades)
        price = (
            sum(t.price * t.quantity for t in trades) / volume
            if volume
            else self.dso.get_market_price(current_step)
        )
        # Apply cash, validation, and DSO accounting for each fill.
        for trade in trades:
            value = trade.price * trade.quantity
            for agent_id, amount in [
                (trade.buyer_id, -value - trade.fees),
                (trade.seller_id, value),
                (self.dso.id, trade.fees),
            ]:
                self.cash_ledger[agent_id] = (
                    self.cash_ledger.get(agent_id, 0.0) + amount
                )
            self.validator.add_trade(trade)
        self.dso.profit = self.get_agent_cash_position(self.dso.id)
        self.dso.congestion_level = self.grid_network.calculate_congestion_level()
        self.dso.balance = grid_balance
        self.dso.balance += sold - sum(
            t.delivered_quantity for t in trades if t.buyer_id == self.dso.id
        )
        self.dso_stats = stats
        self.trades = trades
        result = MatchingResult(
            trades=trades,
            unmatched_orders=[
                replace(o) for o in remaining if o.quantity > self.config._threshold
            ],
            clearing_price=price,
            clearing_volume=volume,
            grid_balance=self.dso.balance,
            grid_congestion=self.dso.congestion_level,
            submitted_orders=[replace(o) for o in orders],
            **{
                key: stats[key]
                for key in (
                    "dso_buy_volume",
                    "dso_sell_volume",
                    "dso_total_volume",
                    "p2p_volume",
                    "dso_trade_ratio",
                    "dso_grid_import",
                    "dso_buy_price",
                    "dso_sell_price",
                    "price_spread",
                    "local_price_avg",
                    "local_price_advantage",
                )
            },
        )
        self.matching_history.update(result)
        if self.config.visualize_blockchain:
            self.validator.visualize_blockchain()
        return result

    # endregion

    # region Position and accounting helpers
    def get_agent_position(self, agent_id: str) -> float:
        """Calculate the net energy position of an agent.

        Args:
            agent_id: Agent identifier

        Returns:
            Net energy position (positive = net seller, negative = net buyer)
        """
        position = 0.0
        agent_trades = [
            trade
            for trade in self.trades
            if trade.buyer_id == agent_id or trade.seller_id == agent_id
        ]

        for trade in agent_trades:
            if trade.seller_id == agent_id:
                position += trade.quantity  # Positive when selling

            if trade.buyer_id == agent_id:
                position -= trade.delivered_quantity  # Negative when buying

        return position

    def calculate_market_statistics(
        self, step: int, trades: List[Trade], dso_stats: Dict
    ) -> Dict:
        """Calculate comprehensive market statistics including DSO and peer-to-peer trading.

        This method analyzes trading activity in both the DSO fallback mechanism and the
        local peer-to-peer market, calculating volumes, prices, and efficiency metrics.

        Args:
            step: Current time step in the simulation
            trades: List of all trades executed in this step
            dso_stats: Dictionary with basic DSO statistics from clear_unmatched_orders method

        Returns:
            Dictionary with comprehensive market statistics
        """
        # Separate DSO and local trades
        local_trades = [
            t
            for t in trades
            if t.buyer_id != self.dso.id and t.seller_id != self.dso.id
        ]

        # Calculate local market metrics
        p2p_volume = sum(t.quantity for t in local_trades)
        local_value = sum(t.price * t.quantity for t in local_trades)

        # Calculate total market volume
        total_volume = dso_stats["dso_total_volume"] + p2p_volume

        # Update the statistics dictionary
        stats = dso_stats.copy()
        stats["p2p_volume"] = p2p_volume
        stats["total_volume"] = total_volume

        # Calculate DSO ratio (proportion of total volume handled by DSO)
        stats["dso_trade_ratio"] = (
            dso_stats["dso_total_volume"] / total_volume if total_volume > 0 else 0.0
        )

        # Get DSO prices for current step
        dso_buy_price = self.dso.get_feed_in_tariff(step)
        dso_sell_price = self.dso.get_utility_price(step)

        # Add DSO price information
        stats["dso_buy_price"] = dso_buy_price
        stats["dso_sell_price"] = dso_sell_price
        stats["price_spread"] = dso_sell_price - dso_buy_price

        # Calculate average local trade price
        if p2p_volume > 0:
            stats["local_price_avg"] = local_value / p2p_volume

            # Calculate local price advantage (positive values indicate local trading is beneficial)
            dso_avg_price = (dso_buy_price + dso_sell_price) / 2
            stats["local_price_advantage"] = dso_avg_price - stats["local_price_avg"]
        else:
            stats["local_price_avg"] = 0.0
            stats["local_price_advantage"] = 0.0

        return stats

    def _create_trade(self, buy_order, sell_order, grid_balance, market_price):
        """Create a partial feasible fill; return None when this pair cannot trade."""
        if (
            buy_order.agent_id == sell_order.agent_id
            or buy_order.price < sell_order.price
            or min(buy_order.quantity, sell_order.quantity) <= self.config._threshold
        ):
            return None, grid_balance
        buyer = buy_order.location.node_id if buy_order.location else None
        seller = sell_order.location.node_id if sell_order.location else None
        routed = buyer is not None and seller is not None
        fraction = (
            self.grid_network.path_delivery_factor(buyer, seller) if routed else 1.0
        )
        if fraction <= 0:
            return None, grid_balance
        quantity = min(sell_order.quantity, buy_order.quantity / fraction)
        if routed:
            quantity = self.grid_network.max_transfer(buyer, seller, quantity)
        if quantity <= self.config._threshold:
            return None, grid_balance
        price = self.config.price_mechanism.get_instance().calculate_price(
            buy_order=buy_order, sell_order=sell_order, reference_price=market_price
        )
        distance = (
            buy_order.location.distance_to(sell_order.location, self.grid_network.graph)
            if routed
            else 0.0
        )
        fees = self.dso.calculate_fees(buy_order, sell_order, price, quantity)
        trade = Trade(
            buy_order.agent_id,
            sell_order.agent_id,
            price,
            quantity,
            max(buy_order.timestamp, sell_order.timestamp),
            distance,
            quantity * (1 - fraction),
            fees,
            buy_order.id,
            sell_order.id,
        )
        if routed and not self.grid_network.update_flow_from_trade(
            buyer, seller, quantity
        ):
            raise ArithmeticError("Previously checked P2P fill became infeasible.")
        buy_order.quantity = max(0.0, buy_order.quantity - trade.delivered_quantity)
        sell_order.quantity = max(0.0, sell_order.quantity - trade.quantity)
        return trade, grid_balance

    def _match_preferred_partners(
        self,
        current_step: int,
        orders: List[Order],
        grid_balance: float,
        market_price: float,
    ) -> Tuple[List[Trade], List[Order]]:
        """Match orders based on explicit partner preferences.

        This method identifies orders with mutual preferences and creates trades between agents
        that have explicitly selected each other as preferred trading partners. These matches
        are processed first, before the price-based matching occurs.

        The strength of preference matching is controlled by the preference_weight parameter
        in the market configuration. Higher values prioritize preferences over price efficiency.

        Args:
            current_step: Current simulation step
            orders: List of orders to match
            grid_balance: Current grid balance (positive means excess supply)
            market_price: Current market price

        Returns:
            Tuple containing (preference_trades, remaining_orders)
        """
        # Initialize result lists
        preference_trades = []
        matched_order_ids = set()

        # STAGE 1: Handle DSO preferences first
        # Separate orders that prefer DSO from others
        dso_preferred_orders = [o for o in orders if o.partner_id == self.dso.id]
        p2p_preferred_orders = [o for o in orders if o.partner_id != self.dso.id]

        # Process DSO-preferred orders through DSO
        if dso_preferred_orders:
            # Separate buy and sell orders that prefer DSO
            dso_preferred_buys = [o for o in dso_preferred_orders if o.is_buy]
            dso_preferred_sells = [o for o in dso_preferred_orders if not o.is_buy]

            # Process through DSO mechanism
            dso_trades, _ = self.dso.clear_unmatched_orders(
                current_step, dso_preferred_buys, dso_preferred_sells
            )

            # Add DSO trades to preference trades
            preference_trades.extend(dso_trades)

            # Mark these orders as matched
            for order in dso_preferred_orders:
                matched_order_ids.add(order.id)

                # Update grid balance based on the trades
                if order.is_buy:
                    grid_balance -= order.quantity  # Buying reduces grid balance
                else:
                    grid_balance += order.quantity  # Selling increases grid balance

        # STAGE 2: Handle peer-to-peer preferences between DER agents
        # Group remaining orders by agent_id to find complementary preferences
        orders_by_agent_id = {}
        for order in p2p_preferred_orders:
            if order.agent_id not in orders_by_agent_id:
                orders_by_agent_id[order.agent_id] = []
            orders_by_agent_id[order.agent_id].append(order)

        # Create a list of potential matches with their scores
        potential_matches = []

        # Find mutual preferences among DER agents
        for order in p2p_preferred_orders:
            # Skip if order has already been matched, or no preference specified, or preferred partner is not in orders_by_agent_id
            if (
                (order.id in matched_order_ids)
                or (order.partner_id is None)
                or (order.partner_id not in orders_by_agent_id)
            ):
                continue

            # Find complementary orders (buy-sell pairs)
            partner_orders = orders_by_agent_id[order.partner_id]
            complementary_orders = [
                o
                for o in partner_orders
                if o.is_buy != order.is_buy and o.partner_id == order.agent_id
            ]

            # If no matching preferences found, continue to next order
            if not complementary_orders:
                continue

            # Determine buy and sell orders for each potential match
            for partner_order in complementary_orders:
                if order.is_buy:
                    buy_order, sell_order = order, partner_order
                else:
                    buy_order, sell_order = partner_order, order

                # Check if this is a valid match
                if not self.dso.validate_grid_constraints(buy_order, sell_order):
                    continue

                # Calculate price efficiency component (lower difference between buy and sell prices = higher efficiency)
                price_difference = buy_order.price - sell_order.price
                max_possible_difference = self.config.max_price - self.config.min_price
                price_score = (
                    1.0 - (price_difference / max_possible_difference)
                    if max_possible_difference > 0
                    else 0.5
                )

                potential_matches.append(
                    {
                        "buy_order": buy_order,
                        "sell_order": sell_order,
                        "score": price_score,
                        "grid_balance": grid_balance,
                    }
                )

        # Sort potential matches by descending score
        potential_matches.sort(key=lambda x: x["score"], reverse=True)

        # Create trades for the best matches
        for match in potential_matches:
            buy_order = match["buy_order"]
            sell_order = match["sell_order"]

            # Skip if either order is already fully matched
            if (buy_order.id in matched_order_ids) or (
                sell_order.id in matched_order_ids
            ):
                continue

            # Skip if quantities are too small
            if (
                buy_order.quantity < self.config._threshold
                or sell_order.quantity < self.config._threshold
            ):
                matched_order_ids.add(buy_order.id)
                matched_order_ids.add(sell_order.id)
                continue

            # Create trade and update grid state
            trade, new_grid_balance = self._create_trade(
                buy_order, sell_order, match["grid_balance"], market_price
            )
            preference_trades.append(trade)

            # Update grid state for subsequent matches
            match["grid_balance"] = new_grid_balance

            # Mark both orders as matched if fully satisfied or if remaining quantity is negligible
            if buy_order.quantity <= self.config._threshold:
                matched_order_ids.add(buy_order.id)

            if sell_order.quantity <= self.config._threshold:
                matched_order_ids.add(sell_order.id)

        # Collect remaining orders (those that weren't completely matched)
        remaining_orders = []
        for order in orders:
            if (order.id not in matched_order_ids) and order.quantity > 0:
                remaining_orders.append(order)

        return preference_trades, remaining_orders

    def get_agent_cash_position(self, agent_id):
        return float(self.cash_ledger.get(agent_id, 0.0))

    # endregion


# endregion
