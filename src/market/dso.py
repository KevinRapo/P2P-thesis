"""
Distribution System Operator (DSO) agent implementation.

This module implements the Distribution System Operator (DSO) agent for the Local Energy Market.
The DSO is responsible for maintaining grid balance, processing unmatched orders, and
collecting grid fees.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
import networkx as nx

from ..grid.network import GridNetwork
from .order import Order, Trade


class DSOAgent:
    """
    Distribution System Operator (DSO) agent for the Local Energy Market.

    The DSO is responsible for:
    1. Grid balance management
    2. Fallback market mechanism for unmatched orders
    3. Grid fee collection (congestion, transmission, imbalance)
    4. Market services (grid constraint validation, dynamic pricing)

    This class centralizes all grid-related operations.
    """

    def __init__(self,
                 id: str = "DSO",
                 feed_in_tariff: Optional[List[float]] = None,
                 utility_price: Optional[List[float]] = None,
                 grid_network: Optional[GridNetwork] = None,
                 max_buy_quantity: Optional[float] = None,
                 max_sell_quantity: Optional[float] = None,
                 node_id: Optional[str] = None,
                 intervention_threshold: float = 0.8,
                 penalty_multiplier: float = 1.0,
                 price_adjustment_factor: float = 0.0,
                 grid_stability_weight: float = 0.5,
                 market_efficiency_weight: float = 0.5,
                 intervention_frequency: float = 0.0,
                 adaptive_threshold: bool = False) -> None:
        """
        Initialize the DSO agent.

        Args:
            id: DSO agent identifier
            feed_in_tariff: Price DSO pays for excess generation ($/kWh)
            utility_price: Price DSO charges for additional demand ($/kWh)
            grid_network: Grid network for congestion and constraint management
        """
        # Initialization
        self.id = id
        self.feed_in_tariff = [] if feed_in_tariff is None else feed_in_tariff
        self.utility_price = [] if utility_price is None else utility_price
        self.grid_network = grid_network  # Grid network for operations
        self.node_id = node_id or (next(iter(grid_network.graph.nodes), None) if grid_network else None)
        self.max_buy_quantity = float("inf") if max_buy_quantity is None else max_buy_quantity
        self.max_sell_quantity = float("inf") if max_sell_quantity is None else max_sell_quantity
        self._capacity_step: Optional[int] = None
        self._remaining_buy_quantity = self.max_buy_quantity
        self._remaining_sell_quantity = self.max_sell_quantity

        # Grid state tracking
        self.balance: float = 0.0
        self.congestion_level: float = 0.0

        # Financial tracking
        self.profit: float = 0.0
        self.fees: float = 0.0

        # Market state tracking
        self.buy_volume: float = 0.0
        self.sell_volume: float = 0.0
        self.total_volume: float = 0.0
        self.grid_import: float = 0.0

        # Intervention thresholds
        self.congestion_threshold: float = 0.8  # Threshold for congestion intervention
        self.voltage_threshold: float = 0.05  # Threshold for voltage drop
        self.instability_threshold: float = 0.2  # Threshold for grid stability

        # Grid fee factors
        self.congestion_factor: float = 0.5  # Factor for congestion fees
        self.distance_factor: float = 0.35  # Factor for distance-based fees
        self.zone_factor: float = 0.15  # Factor for cross-zone fees
        self.voltage_factor: float = 0.15  # Factor for voltage drop fees
        self.imbalance_factor: float = 0.15  # Factor for grid stability fees

        self.intervention_threshold = intervention_threshold
        self.penalty_multiplier = penalty_multiplier
        self.price_adjustment_factor = price_adjustment_factor
        self.grid_stability_weight = grid_stability_weight
        self.market_efficiency_weight = market_efficiency_weight
        self.intervention_frequency = intervention_frequency
        self.adaptive_threshold = adaptive_threshold
        self._rng = np.random.default_rng()
        self._effective_tariffs = {}
        self.intervention_history = []
        self.intervention_active = False
        self.market_price_bounds = (0., float('inf'))
        # Check initialization
        self._check_init()

    def _check_init(self) -> None:
        """Validate the DSO configuration parameters.

        This method checks for consistency of configuration parameters, especially when
        using time-varying price profiles.

        Raises:
            ValueError: If feed_in_tariff is non-positive
            ValueError: If utility_price is non-positive
            ValueError: If both feed_in_tariff and utility_price are time-varying and have different lengths
            ValueError: If feed_in_tariff is greater than utility_price
        """
        for name in ('intervention_threshold','price_adjustment_factor','grid_stability_weight','market_efficiency_weight','intervention_frequency'):
            value=getattr(self,name)
            if not np.isfinite(value) or not 0<=value<=1:
                raise ValueError(f'{name} must be finite and in [0,1].')
        if not np.isclose(self.grid_stability_weight+self.market_efficiency_weight,1.):
            raise ValueError('DSO policy weights must sum to one.')
        if not np.isfinite(self.penalty_multiplier) or self.penalty_multiplier<0:
            raise ValueError('penalty_multiplier must be finite and non-negative.')
        # Allow empty lists for profile management - they will be set by ProfileHandler
        if len(self.feed_in_tariff) == 0:
            raise ValueError("The attribute <feed_in_tariff> cannot be empty.")

        if len(self.utility_price) == 0:
            raise ValueError("The attribute <utility_price> cannot be empty.")

        # Check feed_in_tariff and utility_price have the same length
        if len(self.feed_in_tariff) != len(self.utility_price):
            raise ValueError(f"When both <feed_in_tariff> and <utility_price> are time-varying, they must have the same length (feed_in_tariff: {len(self.feed_in_tariff)}, utility_price: {len(self.utility_price)}).")

        for i, (fit, utility) in enumerate(zip(self.feed_in_tariff, self.utility_price)):
            if fit < 0:
                raise ValueError(f"The <feed_in_tariff[{i}]> ({fit}) must be non-negative.")

            if utility < 0:
                raise ValueError(f"The <utility_price[{i}]> ({utility}) must be non-negative.")

            if fit > utility:
                raise ValueError(f"The <feed_in_tariff[{i}]> ({fit}) must be less than or equal to <utility_price[{i}]> ({utility}).")

    def reset(self, seed: Optional[int] = None) -> None:
        """
        Reset the DSO agent state.
        """
        self._rng = np.random.default_rng(seed)
        self._effective_tariffs = {}
        self.intervention_history = []
        self.intervention_active = False
        self._capacity_step = None
        self._remaining_buy_quantity = self.max_buy_quantity
        self._remaining_sell_quantity = self.max_sell_quantity
        # Reset grid state
        self.balance = 0.0
        self.congestion_level = 0.0

        # Financial tracking
        self.profit = 0.0
        self.fees = 0.0

        # Market state tracking
        self.buy_volume = 0.0
        self.sell_volume = 0.0
        self.total_volume = 0.0
        self.grid_import = 0.0

    def get_feed_in_tariff(self, step: int) -> float:
        """Get the feed-in tariff for a specific time step.

        This method handles both fixed and time-varying feed-in tariff values.
        For time-varying values, it will return the appropriate value for the given time step.

        Args:
            step: Current time step in the simulation

        Returns:
            Feed-in tariff for the specified time step

        Raises:
            IndexError: If using time-varying tariff and step is out of range
        """
        try:
            return self._effective_tariffs.get(step, (self.feed_in_tariff[step], self.utility_price[step]))[0]
        except IndexError:
            raise IndexError(f"Time step {step} is out of range for <feed_in_tariff> with length {len(self.feed_in_tariff)}.")

    def get_utility_price(self, step: int) -> float:
        """Get the utility price for a specific time step.

        This method handles both fixed and time-varying utility price values.
        For time-varying values, it will return the appropriate value for the given time step.

        Args:
            step: Current time step in the simulation

        Returns:
            Utility price for the specified time step

        Raises:
            IndexError: If using time-varying price and step is out of range
        """
        try:
            return self._effective_tariffs.get(step, (self.feed_in_tariff[step], self.utility_price[step]))[1]
        except IndexError:
            raise IndexError(f"Time step {step} is out of range for <utility_price> with length {len(self.utility_price)}.")

    def get_market_price(self, step: int) -> float:
        """Get the market price for a specific time step.

        This method handles both fixed and time-varying market price values.
        For time-varying values, it will return the appropriate value for the given time step.

        Args:
            step: Current time step in the simulation

        Returns:
            Market price for the specified time step

        Raises:
            IndexError: If using time-varying market price and step is out of range
        """
        return (self.get_feed_in_tariff(step) + self.get_utility_price(step)) / 2

    def clear_unmatched_orders(self, step, unmatched_buy_orders, unmatched_sell_orders):
        """Settle bounded fallback fills using the same path/loss model as P2P."""
        if self._capacity_step != step:
            self._capacity_step = step
            self._remaining_buy_quantity = self.max_buy_quantity
            self._remaining_sell_quantity = self.max_sell_quantity
        trades = []
        for order in [*unmatched_sell_orders, *unmatched_buy_orders]:
            if order.quantity <= 1e-9:
                continue
            participant_node = order.location.node_id if order.location else None
            buyer_node, seller_node = ((participant_node,self.node_id) if order.is_buy else (self.node_id,participant_node))
            routed = self.grid_network is not None and buyer_node is not None and seller_node is not None
            fraction = self.grid_network.path_delivery_factor(buyer_node,seller_node) if routed else 1.
            if fraction <= 0:
                continue
            remaining = self._remaining_sell_quantity if order.is_buy else self._remaining_buy_quantity
            source = min(order.quantity/fraction if order.is_buy else order.quantity, remaining)
            if routed:
                source = self.grid_network.max_transfer(buyer_node,seller_node,source)
            if source <= 1e-9:
                continue
            distance = nx.shortest_path_length(self.grid_network.graph,seller_node,buyer_node,weight='weight') if routed else 0.
            trade = Trade(order.agent_id if order.is_buy else self.id,
                          self.id if order.is_buy else order.agent_id,
                          self.get_utility_price(step) if order.is_buy else self.get_feed_in_tariff(step),
                          source,order.timestamp,distance,source*(1-fraction),0.,
                          order.id if order.is_buy else None,None if order.is_buy else order.id)
            trades.append(trade)
            order.quantity = max(0.,order.quantity-(trade.delivered_quantity if order.is_buy else source))
            if order.is_buy:
                self._remaining_sell_quantity -= source
            else:
                self._remaining_buy_quantity -= source
            if routed and not self.grid_network.update_flow_from_trade(buyer_node,seller_node,source):
                raise ArithmeticError('Previously checked DSO fill became infeasible.')
        bought = sum(t.quantity for t in trades if t.buyer_id == self.id)
        sold = sum(t.quantity for t in trades if t.seller_id == self.id)
        profit = sum(t.price*t.quantity*(1 if t.seller_id == self.id else -1) for t in trades)
        self.buy_volume += bought
        self.sell_volume += sold
        self.total_volume += bought+sold
        self.grid_import += sold-bought
        self.profit += profit
        return trades, dict(dso_buy_volume=bought,dso_sell_volume=sold,dso_total_volume=bought+sold,
                            dso_grid_import=sold-bought,dso_profit=profit)

    def calculate_fees(self,
                       buy_order: Order,
                       sell_order: Order,
                       trade_price: float,
                       quantity: float) -> float:
        """Calculate and collect grid-related fees based on grid conditions.

        Args:
            buy_order: Buy order (for single trade fee calculation)
            sell_order: Sell order (for single trade fee calculation)
            trade_price: Base price of the trade ($/kWh) (for single trade fee calculation)
            quantity: Quantity of energy being traded (kWh) (for single trade fee calculation)
            grid_network: GridNetwork object containing grid state information

        Returns:
            Total fees for the trade
        """
        # Initialize fees
        congestion_fee = 0.0
        transmission_fee = 0.0
        imbalance_fee = 0.0
        voltage_fee = 0.0
        thermal_fee = 0.0
        zone_bonus = 0.0

        # Get buyer and seller node IDs if available
        buyer_node = buy_order.location.node_id if buy_order.location else None
        seller_node = sell_order.location.node_id if sell_order.location else None

        # Calculate path-specific congestion if possible, otherwise use global congestion
        if buyer_node and seller_node and self.grid_network:
            try:
                congestion_level = self.grid_network.get_path_congestion(buyer_node, seller_node)
            except nx.NodeNotFound:
                congestion_level = self.grid_network.calculate_congestion_level()
        else:
            # No location information available, use global congestion
            congestion_level = self.grid_network.calculate_congestion_level() if self.grid_network else 0.0

        # Calculate transmission distance and fee
        distance = buy_order.location.distance_to(sell_order.location, self.grid_network.graph) if buy_order.location and sell_order.location and self.grid_network else 0.0

        # Check if buyer and seller are in the same zone and apply bonus
        if buy_order.location and sell_order.location and buy_order.location.zone == sell_order.location.zone:
            # Apply a bonus for same-zone trades (negative fee = bonus)
            zone_bonus = -quantity * trade_price * self.zone_factor  # Negative because it's a bonus

        # Grid congestion fee based on path congestion or global congestion
        if congestion_level > self.congestion_threshold:
            congestion_fee = self.congestion_factor * (congestion_level - self.congestion_threshold) * quantity * trade_price

        # Voltage drop calculation and fee
        voltage_drop = distance * self.voltage_factor
        if voltage_drop > self.voltage_threshold:
            voltage_fee = min(0.2, voltage_drop) * quantity * trade_price

        # Thermal limit fee
        if congestion_level > self.instability_threshold:
            thermal_factor = (congestion_level - self.instability_threshold) / (1.0 - self.instability_threshold)
            thermal_fee = min(0.3, thermal_factor) * quantity * trade_price

        # Calculate imbalance fee based on how the trade affects grid balance
        balance_impact = self._calculate_balance_impact(buy_order.agent_id, sell_order.agent_id, quantity)

        if balance_impact < 0:  # Trade worsens grid balance
            imbalance_fee = abs(balance_impact) * quantity * trade_price * self.imbalance_factor

        # Total all fees
        total_fee = congestion_fee + transmission_fee + imbalance_fee + voltage_fee + thermal_fee + zone_bonus
        total_fee *= self.penalty_multiplier if self.intervention_active else 1.0
        self.fees += total_fee

        return total_fee

    def validate_grid_constraints(self,
                                  buy_order: Order,
                                  sell_order: Order) -> bool:
        """Validate if a potential trade satisfies grid constraints.

        Args:
            buy_order: Buy order
            sell_order: Sell order
            grid_network: GridNetwork object containing grid state information

        Returns:
            Boolean indicating if the trade is valid from a grid perspective
        """
        # Price compatibility check
        if buy_order.price < sell_order.price:
            return False

        # Calculate potential match quantity
        proposed_quantity = min(buy_order.quantity, sell_order.quantity)

        if proposed_quantity <= 0:
            return False

        # Check if trade would exceed grid capacity (using DSO's balance)
        if self.grid_network and abs(self.balance + proposed_quantity) > self.grid_network.capacity:
            return False

        # Get buyer and seller node IDs if available
        buyer_node = buy_order.location.node_id if buy_order.location else None
        seller_node = sell_order.location.node_id if sell_order.location else None

        # Skip path-specific checks if location information is missing
        if not buyer_node or not seller_node or not self.grid_network:
            return True

        # Check path congestion
        try:
            path_congestion = self.grid_network.get_path_congestion(buyer_node, seller_node)
        except nx.NodeNotFound:
            return False

        if path_congestion > self.congestion_threshold:
            return False

        return True

    def _calculate_balance_impact(self,
                                  buyer_id: str,
                                  seller_id: str,
                                  quantity: float) -> float:
        """Calculate the impact of a trade on grid balance.

        Positive values mean the trade helps balance the grid.
        Negative values mean the trade worsens grid imbalance.

        Args:
            buyer_id: ID of the buyer agent
            seller_id: ID of the seller agent
            quantity: Quantity of energy being traded (kWh)

        Returns:
            Balance impact score (-1 to 1 scale)
        """
        # If grid has excess supply (positive balance)
        if self.balance > 0:
            # Any consumption helps balance
            if buyer_id != self.id and seller_id != self.id:
                # P2P trade doesn't directly affect grid balance
                return 0.0
            elif buyer_id == self.id:
                # DSO buying energy (consuming excess) helps balance
                impact = min(quantity / abs(self.balance), 1.0)
                return impact
            else:
                # DSO selling energy (adding to excess) worsens balance
                impact = -min(quantity / abs(self.balance), 1.0)
                return impact

        # If grid has excess demand (negative balance)
        elif self.balance < 0:
            # Any generation helps balance
            if buyer_id != self.id and seller_id != self.id:
                # P2P trade doesn't directly affect grid balance
                return 0.0
            elif seller_id == self.id:
                # DSO selling energy (providing shortage) helps balance
                impact = min(quantity / abs(self.balance), 1.0)
                return impact
            else:
                # DSO buying energy (adding to shortage) worsens balance
                impact = -min(quantity / abs(self.balance), 1.0)
                return impact

        # Grid is perfectly balanced
        return 0.0

    def prepare_period(self, step):
        """Decide intervention once using last congestion and current net demand.

        Frequency is a seeded per-period activation probability above threshold.
        Adaptive policies lower their threshold under higher physical pressure.
        This explicit abstract controller implements the Case 3 configuration;
        it is not a voltage or AC stability controller.
        """
        capacity=self.grid_network.capacity*self.grid_network.time_step_hours if self.grid_network else 1.
        pressure=min(1.,max(self.congestion_level,abs(self.balance)/max(capacity,1e-12)))
        threshold=self.intervention_threshold*(1.-.25*pressure) if self.adaptive_threshold else self.intervention_threshold
        self.intervention_active=bool(pressure>=threshold and self._rng.random()<self.intervention_frequency)
        fit,utility=self.feed_in_tariff[step],self.utility_price[step]
        if self.intervention_active:
            adjustment=self.price_adjustment_factor*pressure*self.grid_stability_weight
            if self.balance<0:
                utility*=1.+adjustment
                fit*=1.+adjustment*self.market_efficiency_weight
            else:
                fit*=1.-adjustment
                utility*=1.-adjustment*self.market_efficiency_weight
        low,high=self.market_price_bounds
        fit=float(np.clip(fit,low,high)); utility=float(np.clip(utility,max(low,fit),high))
        self._effective_tariffs[step]=(fit,utility)
        self.intervention_history.append(dict(step=step,pressure=pressure,threshold=threshold,
                                             active=self.intervention_active,feed_in_tariff=fit,utility_price=utility))
