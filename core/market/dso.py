"""The DSO: the market maker of last resort and the grid's operator ([P1] §3.3.1).

What belongs to the DSO and nobody else:

    tariffs          p_FiT, what it pays for energy it buys, and p_utility, what it
                     charges for energy it sells; p_FiT < p_P2P < p_utility
    market price     the midpoint of the two, the reference before any trade
    grid             what it saw in the step's power flow: the lines' loading
    losses, fees     eq. 18 for every trade as it clears; eq. 8 once the step's
                     power flow is known, and who pays them
    stage 3          it buys every remaining sell at p_FiT and sells every
                     remaining buy at p_utility, so every order clears (§3.3.2)
    balance          eq. 7, its energy sold minus bought, and its money

[P1] gives the fee factors no values and F_trans no formula; the choices are in
``Dso.fees_of``, ``Dso.imbalance_fee`` and ``Dso.charge``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Mapping, Optional, Sequence

from core.grid.contract import GridAssessment, GridPath
from core.market.order import GridFees, Order, Trade

DSO_ID = "DSO"


@dataclass(frozen=True)
class DsoOutcome:
    """What the DSO did in one step.

    Attributes:
        bought_kwh: Energy it bought from participants (stage 3).
        sold_kwh: Energy it sold to participants (stage 3).
        balance_kwh: Eq. 7 for this step: sold − bought (+ the market imports).
        energy_revenue: What it was paid for energy minus what it paid.
        fees: Fees it collected from every trade (0 when not charged).
        profit: Energy revenue plus fees.
    """

    bought_kwh: float
    sold_kwh: float
    balance_kwh: float
    energy_revenue: float
    fees: float
    profit: float


class Dso:
    """The DSO of one market day.

    Args:
        feed_in_tariff: p_FiT, what the DSO pays per kWh it buys ([P1] §3.3.1).
        utility_price: p_utility, what the DSO charges per kWh it sells ([P1]
            §3.3.1).
        fees_charged: Whether the participants pay the fees.
        fee_buyer_share: Share of a peer-to-peer fee the buyer pays.
        loss_factor: κ of eq. 18, per km.
        congestion_factor: f_cong of eq. 8a.
        congestion_threshold: C_threshold of eq. 8a.
        voltage_factor: f_volt of eq. 8f, per km.
        voltage_threshold: V_threshold of eq. 8c.
        thermal_threshold: T_threshold of eq. 8g.
        thermal_cap: f_threshold of eq. 8d.
        imbalance_factor: f_imb of eq. 8b.
        zone_factor: f_zone of eq. 8e.
        voltage_drop: V_drop of eq. 8c: ``"distance"`` (eq. 8f) or ``"measured"``
            (between the path's two buses in the step's power flow).
        id: The DSO's ID in trades and partner preferences.
    """

    def __init__(
        self,
        feed_in_tariff: float,
        utility_price: float,
        fees_charged: bool = True,
        fee_buyer_share: float = 0.5,
        loss_factor: float = 0.03,
        congestion_factor: float = 0.5,
        congestion_threshold: float = 0.8,
        voltage_factor: float = 0.15,
        voltage_threshold: float = 0.05,
        thermal_threshold: float = 0.2,
        thermal_cap: float = 0.3,
        imbalance_factor: float = 0.15,
        zone_factor: float = 0.15,
        voltage_drop: str = "distance",
        id: str = DSO_ID,
    ) -> None:
        if voltage_drop not in ("distance", "measured"):
            raise ValueError("voltage_drop must be 'distance' or 'measured'")

        self.feed_in_tariff = feed_in_tariff
        self.utility_price = utility_price
        self.fees_charged = fees_charged
        self.fee_buyer_share = fee_buyer_share
        self.loss_factor = loss_factor
        self.congestion_factor = congestion_factor
        self.congestion_threshold = congestion_threshold
        self.voltage_factor = voltage_factor
        self.voltage_threshold = voltage_threshold
        self.thermal_threshold = thermal_threshold
        self.thermal_cap = thermal_cap
        self.imbalance_factor = imbalance_factor
        self.zone_factor = zone_factor
        self.voltage_drop = voltage_drop
        self.id = id
        self.line_loading_percent: Mapping[str, float] = {}
        self.bus_voltage_pu: Mapping[str, float] = {}
        self.balance_kwh = 0.0
        self.profit = 0.0
        self.fees = 0.0

    def reset(self) -> None:
        """Back to the start of the day: nothing seen of the grid, balance 0."""
        self.line_loading_percent = {}
        self.bus_voltage_pu = {}
        self.balance_kwh = 0.0
        self.profit = 0.0
        self.fees = 0.0

    # --- Tariffs ---------------------------------------------------------------------
    def market_price(self) -> float:
        """The midpoint of p_FiT and p_utility: the reference price before any
        peer-to-peer trade (the original's ``get_market_price``; not in [P1])."""
        return (self.feed_in_tariff + self.utility_price) / 2

    # --- The grid it operates --------------------------------------------------------
    def observe(
        self, grid: GridAssessment, measured: Optional[GridAssessment] = None
    ) -> None:
        """Remember the lines' loading of the step (``grid``: the power flow just
        run, or the graph model's): the congestion the same step's fees see ([P1]
        §3.5.3); and the bus voltages of the power flow (``measured``, default
        ``grid``) for a measured voltage drop."""
        self.line_loading_percent = dict(grid.line_loading_percent)
        self.bus_voltage_pu = dict((measured or grid).bus_voltage_pu)

    def voltage_drop_of(self, path: GridPath) -> float:
        """V_drop of a trade ([P1] eq. 8c): f_volt · d_ij (eq. 8f), or the measured
        |V_a − V_b| between the path's two buses (0 when not known)."""
        if self.voltage_drop == "distance":
            return self.voltage_factor * path.distance_km

        a = self.bus_voltage_pu.get(path.bus_a)
        b = self.bus_voltage_pu.get(path.bus_b)

        return abs(a - b) if a is not None and b is not None else 0.0

    def congestion(self, lines: Sequence[str]) -> float:
        """C_t of a trade ([P1] eq. 8a): the highest loading on its path in the
        step's power flow, 0 to 1. 0 without lines, or when the flow did not
        converge (no loadings)."""
        loading = [self.line_loading_percent.get(line, 0.0) for line in lines]
        return min(1.0, max(loading, default=0.0) / 100)

    def transmission_loss(self, distance_km: float, quantity: float) -> float:
        """[P1] eq. 18: l_ij = d_ij · q_ij · κ."""
        return distance_km * quantity * self.loss_factor

    # --- Fees (eq. 8) ----------------------------------------------------------------
    def fees_of(
        self, quantity: float, price: float, path: GridPath, loss_kwh: float
    ) -> GridFees:
        """[P1] eq. 8 for a peer-to-peer trade of ``quantity`` at ``price`` along
        ``path``. F_trans has no formula in [P1]: here it is the lost energy at the
        trade price ("the loss ... is included in the DSO fees", §3.5.2). F_imb
        is 0: eq. 8h gives a balance impact only to trades with the DSO."""
        value = quantity * price
        c = self.congestion(path.lines)
        congestion = 0.0

        if c > self.congestion_threshold:  # 8a
            congestion = self.congestion_factor * (c - self.congestion_threshold)
            congestion *= value

        thermal = 0.0

        if c > self.thermal_threshold:  # 8g, 8d
            f_thermal = (c - self.thermal_threshold) / (1 - self.thermal_threshold)
            thermal = min(f_thermal, self.thermal_cap) * value

        v_drop = self.voltage_drop_of(path)  # 8f, or measured

        return GridFees(
            congestion=congestion,
            transmission=loss_kwh * price,
            voltage=min(v_drop, self.voltage_threshold) * value,  # 8c
            thermal=thermal,
            zone=-self.zone_factor * value if path.same_zone else 0.0,  # 8e
        )

    def imbalance_fee(self, trade: Trade, grid_balance_kwh: float) -> GridFees:
        """[P1] eq. 8b with 8h for a trade with the DSO: B_impact = ±min(q / |B|, 1)
        on the market's balance B (+ excess supply). Charged only when the trade
        worsens the balance (the DSO buys during excess demand or sells during
        excess supply); a trade that helps pays nothing, as in the original."""
        if abs(grid_balance_kwh) < 1e-9:
            return GridFees()

        dso_buys = trade.buyer_id == self.id
        helps = dso_buys == (grid_balance_kwh > 0)

        if helps:
            return GridFees()

        impact = min(trade.quantity / abs(grid_balance_kwh), 1.0)
        value = trade.quantity * trade.price

        return GridFees(imbalance=self.imbalance_factor * impact * value)

    def _charged(self, trade: Trade, parts: GridFees) -> Trade:
        """The trade with its fee, split between who pays it: the buyer's share of
        a peer-to-peer fee, the participant's whole fee with the DSO. Nothing is
        paid when the fees are not charged."""
        total = parts.total

        if not self.fees_charged:
            buyer = seller = 0.0
        elif trade.buyer_id == self.id:
            buyer, seller = 0.0, total
        elif trade.seller_id == self.id:
            buyer, seller = total, 0.0
        else:
            buyer = total * self.fee_buyer_share
            seller = total - buyer

        return replace(
            trade, fees=total, fee_parts=parts, buyer_fee=buyer, seller_fee=seller
        )

    def assess(self, trade: Trade, path: GridPath) -> Trade:
        """A trade with its distance d_ij ([P1] §3.5.1) and loss l_ij (eq. 18),
        as it clears. Its fee (eq. 8) follows the step's power flow (``charge``)."""
        loss = self.transmission_loss(path.distance_km, trade.quantity)
        return replace(trade, distance=path.distance_km, transmission_loss=loss)

    def trade_path(
        self,
        trade: Trade,
        path: Callable[[str, str], GridPath],
        upstream: Callable[[str], GridPath],
    ) -> GridPath:
        """The peer path, or the participant's upstream path for a DSO trade."""
        if self.id in (trade.buyer_id, trade.seller_id):
            other = trade.seller_id if trade.buyer_id == self.id else trade.buyer_id
            return upstream(other)
        return path(trade.buyer_id, trade.seller_id)

    def charge(
        self,
        trades: Sequence[Trade],
        path: Callable[[str, str], GridPath],
        upstream: Callable[[str], GridPath],
        grid_balance_kwh: float = 0.0,
    ) -> tuple[Trade, ...]:
        """Every trade of the step with its fee (eq. 8), after the step's power
        flow (``observe``): the congestion and thermal parts see the loading that
        these trades, with everything else on the network, actually caused.

        A peer-to-peer trade runs along ``path(buyer, seller)``. A trade with the
        DSO runs along ``upstream(participant)``, the path to the transformer's
        busbar, without a zone bonus (the DSO is in no participant's zone), and
        pays the imbalance fee (eq. 8b) when it worsens the market's balance
        ``grid_balance_kwh`` (B_grid before stage 3, + excess supply)."""
        out = []

        for t in trades:
            parts = self.fees_of(
                t.quantity,
                t.price,
                self.trade_path(t, path, upstream),
                t.transmission_loss,
            )
            if self.id in (t.buyer_id, t.seller_id):
                imbalance = self.imbalance_fee(t, grid_balance_kwh).imbalance
                parts = replace(parts, zone=0.0, imbalance=imbalance)
            out.append(self._charged(t, parts))

        return tuple(out)

    # --- Stage 3 - clearing-----------------------------------------------------------
    def clear(
        self,
        orders: Sequence[Order],
        upstream: Callable[[str], GridPath] = lambda participant: GridPath(),
    ) -> tuple[Trade, ...]:
        """Stage 3 ([P1] §3.3.2): buy every remaining sell at p_FiT and sell every
        remaining buy at p_utility.

        The DSO's energy enters where the upstream grid feeds the network, so a
        trade with it runs along ``upstream(participant)``, the path to the
        transformer's busbar: it has a distance and a loss (eq. 18) like a peer
        trade. Its fees (eq. 8, with the imbalance fee) follow the step's power
        flow (``charge``)."""
        trades = []

        for o in orders:
            if o.is_buy:
                buyer, seller, price = o.agent_id, self.id, self.utility_price
            else:
                buyer, seller, price = self.id, o.agent_id, self.feed_in_tariff
            trade = Trade(buyer, seller, price, o.quantity, o.timestamp, stage=3)
            trades.append(self.assess(trade, upstream(o.agent_id)))

        return tuple(trades)

    # --- Balance (eq. 7) -------------------------------------------------------------
    def settle(self, trades: Sequence[Trade]) -> DsoOutcome:
        """The DSO's step: eq. 7, B_DSO = Σ (E_sold − E_bought), its energy
        revenue and the fees it collected; added to its running totals."""
        bought = sum(t.quantity for t in trades if t.buyer_id == self.id)
        sold = sum(t.quantity for t in trades if t.seller_id == self.id)
        revenue = sum(t.price * t.quantity for t in trades if t.seller_id == self.id)
        revenue -= sum(t.price * t.quantity for t in trades if t.buyer_id == self.id)
        fees = sum(t.buyer_fee + t.seller_fee for t in trades)
        self.balance_kwh += sold - bought
        self.profit += revenue + fees
        self.fees += fees

        return DsoOutcome(
            bought_kwh=bought,
            sold_kwh=sold,
            balance_kwh=sold - bought,
            energy_revenue=revenue,
            fees=fees,
            profit=revenue + fees,
        )
