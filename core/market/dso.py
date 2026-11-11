"""The DSO: the market maker of last resort and the grid's operator ([P1] §3.3.1).

What belongs to the DSO and nobody else:

    tariffs          p_FiT, what it pays for energy it buys, and p_utility, what it
                     charges for energy it sells; p_FiT < p_P2P < p_utility. Flat,
                     or hourly series: ``set_hour`` sets the step's
    market price     the midpoint of the two, the reference before any trade
    grid             what it saw in the step's power flow: the lines' and the
                     transformer's loading, the bus voltages
    losses, fees     eq. 18 for every trade as it clears; eq. 8 once the step's
                     power flow is known, and who pays them; the same fees for the
                     energy no trade covered, settled with it at the tariffs
    stage 3          it buys every remaining sell at p_FiT and sells every
                     remaining buy at p_utility, so every order clears (§3.3.2)
    balance          eq. 7, its energy sold minus bought, and its money

[P1] gives the fee factors no values and F_trans no formula; the choices are in
``Dso.fees_of``, ``Dso.imbalance_fee`` and ``Dso.charge``.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Callable, Mapping, Optional, Sequence

from core.config.scenario import DsoSetup, load_prices, price_at
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
        fees: Fees it collected from every trade, and the participants' loss
            charges (0 when not charged).
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
        setup: Tariffs and fee parameters (``DsoSetup``), copied so later edits
            to the caller's settings do not change this DSO. The current hourly
            tariffs, observed grid and running totals are kept separately.
        step_hours: Hours per market step, which the price series must match.
        id: The DSO's ID in trades and partner preferences.
    """

    def __init__(
        self,
        setup: DsoSetup,
        step_hours: float = 1.0,
        id: str = DSO_ID,
    ) -> None:
        if setup.voltage_drop not in ("distance", "measured"):
            raise ValueError("voltage_drop must be 'distance' or 'measured'")

        self.setup = deepcopy(setup)
        self.prices = load_prices(self.setup.prices, step_hours)
        self.day_prices = self.prices
        self.step_hours = step_hours
        self.feed_in_tariff, self.utility_price = self.tariffs_at(0.0)
        self.id = id
        self.line_loading_percent: Mapping[str, float] = {}
        self.trafo_loading_percent = 0.0
        self.bus_voltage_pu: Mapping[str, float] = {}
        self.slack_voltage_pu = 1.0
        self.balance_kwh = 0.0
        self.profit = 0.0
        self.fees = 0.0

    def reset(self) -> None:
        """Back to the start of the day: nothing seen of the grid, balance 0."""
        self.line_loading_percent = {}
        self.trafo_loading_percent = 0.0
        self.bus_voltage_pu = {}
        self.slack_voltage_pu = 1.0
        self.balance_kwh = 0.0
        self.profit = 0.0
        self.fees = 0.0

    # --- Tariffs ---------------------------------------------------------------------
    def prices_of(self, day: str) -> dict:
        """The series of ``day`` ("YYYY-MM-DD"): its own in a file with ``days``."""
        days = self.prices.get("days")

        if days is None:
            return self.prices

        if day not in days:
            raise ValueError(f"The prices have no day {day}")

        return days[day]

    def set_day(self, day: str) -> None:
        """Trade at the prices of ``day`` from now on."""
        self.day_prices = self.prices_of(day)

    def tariffs_at(
        self, hour: float, prices: Optional[dict] = None
    ) -> tuple[float, float]:
        """``(p_FiT, p_utility)`` at ``hour`` of the current day, or of ``prices``
        (a day's series)."""
        day = prices or self.day_prices

        return price_at(day["feed_in"], hour), price_at(day["utility"], hour)

    def set_hour(self, hour: float) -> None:
        """Make the tariffs of ``hour`` the current ones (``feed_in_tariff``,
        ``utility_price``): what the step about to be played trades at."""
        self.feed_in_tariff, self.utility_price = self.tariffs_at(hour)

    def tariff_range(self, days: Sequence[str] = ()) -> tuple[float, float]:
        """The lowest p_FiT and the highest p_utility over ``days`` (default: the
        current day): the fixed range prices are scaled by (observation, reward)."""
        steps = range(round(24 / self.step_hours))
        series = [self.prices_of(day) for day in days] or [self.day_prices]
        prices = [
            self.tariffs_at(step * self.step_hours, day)
            for day in series
            for step in steps
        ]

        return min(f for f, _ in prices), max(u for _, u in prices)

    def peer_ceiling(self) -> float:
        """The highest peer-to-peer price: above it the buyer, who pays the peer
        charge on top, would pay more than the DSO asks. The utility price when the
        fees are not charged."""
        charge = self.setup.peer_charge_kwh if self.setup.fees_charged else 0.0

        return self.utility_price - charge

    def market_price(self) -> float:
        """The midpoint of p_FiT and the peer ceiling: the reference price before any
        peer-to-peer trade (the original's ``get_market_price``; not in [P1]); with
        no peer charge, of the two tariffs."""
        return (self.feed_in_tariff + self.peer_ceiling()) / 2

    # --- The grid it operates --------------------------------------------------------
    def observe(self, grid: GridAssessment) -> None:
        """Remember the step's power flow (``grid``, just run): the lines' and the
        transformer's loading, the congestion the same step's fees see ([P1]
        §3.5.3), and the bus voltages and the voltage the network is held at (the
        external grid's set point) for a measured voltage drop."""
        self.line_loading_percent = dict(grid.line_loading_percent)
        self.trafo_loading_percent = float(grid.max_trafo_loading_percent or 0.0)
        self.bus_voltage_pu = dict(grid.bus_voltage_pu)
        slack = grid.slack_voltage_pu
        self.slack_voltage_pu = 1.0 if slack is None else float(slack)

    def voltage_drop_of(self, path: GridPath) -> float:
        """V_drop of a trade ([P1] eq. 8c): f_volt · d_ij (eq. 8f), or, measured,
        the largest deviation from the voltage the network is held at,
        max |V − V_slack| over the buses on the path (the two ends when the path does
        not list its buses; 0 when not known, so without a power flow).
        V_slack is the external grid's set point (``GridAssessment.slack_voltage_pu``),
        1.025 pu on SimBench's networks: the deviation from nominal 1 pu would charge
        every trade at least that, with nothing drawn from the network at all (MP-4l).
        The measured value is not the difference between the ends either: on a feeder
        whose voltage is high all along, as rural1's is when it exports, two
        neighbours at 1.05 pu differ by nothing but the voltage limit binds."""
        if self.setup.voltage_drop == "distance":
            return self.setup.voltage_factor * path.distance_km

        buses = path.buses or (path.bus_a, path.bus_b)
        found = [self.bus_voltage_pu[b] for b in buses if b in self.bus_voltage_pu]

        return max((abs(v - self.slack_voltage_pu) for v in found), default=0.0)

    def congestion(self, lines: Sequence[str], transformer: bool = False) -> float:
        """C_t of a trade ([P1] eq. 8a): the highest loading on its path in the
        step's power flow, 0 to 1. A trade with the DSO runs up to the transformer
        (``transformer``), which counts as part of its path: its loading is
        compared with the lines'. 0 without lines, or when the flow did not
        converge (no loadings)."""
        loading = [self.line_loading_percent.get(line, 0.0) for line in lines]

        if transformer:
            loading.append(self.trafo_loading_percent)

        return min(1.0, max(loading, default=0.0) / 100)

    def transmission_loss(self, distance_km: float, quantity: float) -> float:
        """[P1] eq. 18: l_ij = d_ij · q_ij · κ."""
        return distance_km * quantity * self.setup.loss_factor

    # --- Fees (eq. 8) ----------------------------------------------------------------
    def fees_of(  #! Market 6: fee parts (eq. 8)
        self,
        quantity: float,
        price: float,
        path: GridPath,
        loss_kwh: float,
        transformer: bool = False,
    ) -> GridFees:
        """[P1] eq. 8 for a trade of ``quantity`` at ``price`` along ``path``; with
        the DSO, ``transformer`` adds the transformer to the path's congestion.
        F_trans has no formula in [P1]: here it is the lost energy at the
        trade price ("the loss ... is included in the DSO fees", §3.5.2), with
        ``losses = "trades"``; with a power-flow loss rule the losses are charged
        per participant instead (``loss_charge``), and F_trans is 0. F_imb is 0:
        eq. 8h gives a balance impact only to trades with the DSO (``charge``).

        The zone bonus (eq. 8e) cancels fees but never pays out: it is at most the
        sum of the other parts, so a trade's fee is never below 0 (MP-4n)."""
        s = self.setup
        value = quantity * price
        c = self.congestion(path.lines, transformer)
        congestion = 0.0

        if c > s.congestion_threshold:  # 8a
            congestion = s.congestion_factor * (c - s.congestion_threshold)
            congestion *= value

        thermal = 0.0

        if c > s.thermal_threshold:  # 8g, 8d
            f_thermal = (c - s.thermal_threshold) / (1 - s.thermal_threshold)
            thermal = min(f_thermal, s.thermal_cap) * value

        v_drop = self.voltage_drop_of(path)  # 8f, or measured
        transmission = loss_kwh * price if s.losses == "trades" else 0.0
        voltage = min(v_drop, s.voltage_threshold) * value  # 8c
        charges = congestion + transmission + voltage + thermal
        bonus = min(s.zone_factor * value, charges) if path.same_zone else 0.0

        return GridFees(
            congestion=congestion,
            transmission=transmission,
            voltage=voltage,
            thermal=thermal,
            zone=-bonus,  # 8e, capped at the fees it cancels
            peer_charge=s.peer_charge_kwh * quantity,
        )

    def imbalance_fee(self, trade: Trade, grid_balance_kwh: float) -> GridFees:
        """[P1] eq. 8b with 8h for a trade with the DSO: B_impact = ±min(q / |B|, 1)
        on the market's balance B (+ excess supply). Charged only when the trade
        worsens the balance (the DSO buys during excess demand or sells during
        excess supply); a trade that helps pays nothing, as in the original.

        B is the order book's balance before stage 3 (offered minus asked), not a
        physical quantity, so the fee lands on the minority side of the book (the
        leftover buyers when the book is long, as at midday), and only the sign
        of a net that no single agent sees or controls decides who pays; near a
        balanced book the scale q / |B| saturates at 1. Off in the thesis scenario
        (``imbalance_factor`` 0)."""
        # OPEN MP-4m: keep the fee off for the thesis, or replace it (a flat charge
        # on the DSO-routed quantity, or a fee on min(q, |B|)); see open.md.
        if abs(grid_balance_kwh) < 1e-9:
            return GridFees()

        dso_buys = trade.buyer_id == self.id
        helps = dso_buys == (grid_balance_kwh > 0)

        if helps:
            return GridFees()

        impact = min(trade.quantity / abs(grid_balance_kwh), 1.0)
        value = trade.quantity * trade.price

        return GridFees(imbalance=self.setup.imbalance_factor * impact * value)

    def _charged(self, trade: Trade, parts: GridFees) -> Trade:
        """The trade with its fee, split between who pays it: the buyer's share of
        a peer-to-peer fee and the whole peer charge, the participant's whole fee
        with the DSO. Nothing is paid when the fees are not charged."""
        total = parts.total

        if not self.setup.fees_charged:
            buyer = seller = 0.0
        elif trade.buyer_id == self.id:
            buyer, seller = 0.0, total
        elif trade.seller_id == self.id:
            buyer, seller = total, 0.0
        else:
            shared = total - parts.peer_charge
            seller = shared * (1.0 - self.setup.fee_buyer_share)
            buyer = total - seller

        return replace(
            trade, fees=total, fee_parts=parts, buyer_fee=buyer, seller_fee=seller
        )

    def assess(self, trade: Trade, path: GridPath) -> Trade:
        """A trade with its distance d_ij ([P1] §3.5.1) and loss l_ij (eq. 18),
        as it clears. Its fee (eq. 8) follows the step's power flow (``charge``)."""
        loss = self.transmission_loss(path.distance_km, trade.quantity)
        return replace(trade, distance=path.distance_km, transmission_loss=loss)

    def charge(
        self,
        trades: Sequence[Trade],
        route: Callable[[str, str], GridPath],
        grid_balance_kwh: float = 0.0,
    ) -> tuple[Trade, ...]:
        """Every trade of the step with its fee (eq. 8), after the step's power
        flow (``observe``): the congestion and thermal parts see the loading that
        these trades, with everything else on the network, actually caused.

        A trade runs along ``route(buyer, seller)``: for a peer-to-peer trade the
        path between them, for a trade with the DSO the participant's path to the
        transformer's busbar. The latter has no zone bonus (the DSO is in no
        participant's zone) and pays the imbalance fee (eq. 8b) when it worsens
        the market's balance ``grid_balance_kwh`` (B_grid before stage 3, + excess
        supply)."""
        out = []

        for t in trades:
            with_dso = self.id in (t.buyer_id, t.seller_id)
            parts = self.fees_of(
                t.quantity,
                t.price,
                route(t.buyer_id, t.seller_id),
                t.transmission_loss,
                transformer=with_dso,
            )
            if with_dso:
                imbalance = self.imbalance_fee(t, grid_balance_kwh).imbalance
                parts = replace(
                    parts, zone=0.0, imbalance=imbalance, peer_charge=0.0
                )
            out.append(self._charged(t, parts))

        return tuple(out)

    # --- Stage 3 - clearing-----------------------------------------------------------
    def clear(
        self,
        orders: Sequence[Order],
        route: Callable[[str, str], GridPath] = lambda a, b: GridPath(),
    ) -> tuple[Trade, ...]:
        """Stage 3 ([P1] §3.3.2): buy every remaining sell at p_FiT and sell every
        remaining buy at p_utility.

        The DSO's energy enters where the upstream grid feeds the network, so a
        trade with it runs along ``route(buyer, seller)``, which for the DSO is the
        participant's path to the transformer's busbar: it has a distance and a
        loss (eq. 18) like a peer trade. Its fees (eq. 8, with the imbalance fee) follow the step's power
        flow (``charge``)."""
        trades = []

        for o in orders:
            if o.is_buy:
                buyer, seller, price = o.agent_id, self.id, self.utility_price
            else:
                buyer, seller, price = self.id, o.agent_id, self.feed_in_tariff
            trade = Trade(buyer, seller, price, o.quantity, o.timestamp, stage=3)
            trades.append(self.assess(trade, route(buyer, seller)))

        return tuple(trades)

    # --- Balance (eq. 7) -------------------------------------------------------------
    def loss_charge(self, share_kwh: float, utility_price: float) -> float:
        """What a participant pays for its share of the step's measured losses: the
        energy at the step's utility price, the price of energy from upstream,
        which is where the losses are supplied from; a negative share is paid
        back. Nothing is paid when the fees are not charged."""
        if not self.setup.fees_charged:
            return 0.0
        return share_kwh * utility_price

    def settle(  #! Market 7: DSO balance
        self,
        trades: Sequence[Trade],
        loss_charges: float = 0.0,
        untraded: Sequence[Trade] = (),
    ) -> DsoOutcome:
        """The DSO's step: eq. 7, B_DSO = Σ (E_sold − E_bought), its energy
        revenue and the fees it collected, the participants' loss charges and the
        fees of their untraded energy included (not its energy: that is settled
        outside the market, MP-1e); added to its running totals."""
        bought = sum(t.quantity for t in trades if t.buyer_id == self.id)
        sold = sum(t.quantity for t in trades if t.seller_id == self.id)
        revenue = sum(t.price * t.quantity for t in trades if t.seller_id == self.id)
        revenue -= sum(t.price * t.quantity for t in trades if t.buyer_id == self.id)
        fees = sum(t.buyer_fee + t.seller_fee for t in (*trades, *untraded))
        fees += loss_charges
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
