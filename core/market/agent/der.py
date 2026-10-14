"""A participant (the paper's DER agent): its profiles, battery and accounts.

[P1] §3.4. What belongs to one participant and nobody else:

    profiles      G_t and D_t from the network elements it took over
    feasibility   eq. 15a-b: the most it may sell or buy this step
    partner       the rule-based preferred partner (§3.4, phase 2 of §3.9)
    settlement    eq. 13 (balance), eq. 14 (profit), the battery (eq. 16); its
                  grid fees once the step's power flow is known
    reputation    its r_i, as the reputation module last set it (eq. 12, §3.3.4;
                  ``core/market/reputation.py``)
    injection     its power at its bus, for the power flow

The market decides the trades; the participant turns them into what it physically
did and what it earned.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Mapping, Optional, Sequence

from core.grid.contract import ParticipantInjection
from core.market.agent.battery import Battery
from core.market.order import Trade


# --------------------------------------------------------------------------------------
# What a participant did in one step
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ParticipantOutcome:
    """What one participant did in one step ([P1] eq. 13, 14, 16).

    Attributes:
        generation_kwh, demand_kwh: Own generation and demand.
        bought_kwh, sold_kwh: Energy traded (with peers and the DSO).
        charge_kwh: Energy the battery drew from the bus.
        discharge_kwh: Energy the battery delivered to the bus.
        external_kwh: Energy no trade covers: + exported, − imported.
        soc_kwh: Battery energy after the step (``None``: no battery).
        balance_kwh: Eq. 13: (G − D) + (bought − sold).
        fees: Grid fees it paid this step (eq. 8; its share of each trade's).
        profit: Eq. 14 for this step: revenue − cost of its trades − fees.
    """

    participant_id: str
    generation_kwh: float
    demand_kwh: float
    bought_kwh: float
    sold_kwh: float
    charge_kwh: float
    discharge_kwh: float
    external_kwh: float
    soc_kwh: Optional[float]
    balance_kwh: float
    fees: float
    profit: float

    # [P1] §3.4.1 tracks "the total demand satisfied versus the demand deferred".
    # The DSO clears every order, so no demand goes unmet physically; deferred is
    # what the participant's own orders and battery left uncovered, exchanged with
    # the upstream grid untraded (``external_kwh``).
    @property
    def deferred_demand_kwh(self) -> float:
        """Demand that generation, purchases and battery discharge did not cover."""
        return max(0.0, -self.external_kwh)

    @property
    def satisfied_demand_kwh(self) -> float:
        """Demand covered by generation, purchases and battery discharge."""
        return self.demand_kwh - self.deferred_demand_kwh

    @property
    def deferred_supply_kwh(self) -> float:
        """Generation that demand, sales and battery charge did not take up."""
        return max(0.0, self.external_kwh)

    @property
    def satisfied_supply_kwh(self) -> float:
        """Generation taken up by demand, sales and battery charge."""
        return self.generation_kwh - self.deferred_supply_kwh


# --------------------------------------------------------------------------------------
# Profiles from network elements
# --------------------------------------------------------------------------------------
def profiles_from_elements(
    owns: Sequence[str],
    kinds: Mapping[str, str],
    power_kw: Mapping[str, Sequence[float]],
    step_hours: float,
    n_steps: int,
) -> tuple[list[float], list[float]]:
    """A participant's generation and demand per step (kWh): its generators
    (``sgen``) add to G_t, its loads to D_t ([P1] §3.4.4). Storage elements are
    left out: the participant's battery takes their place.

    Args:
        owns: The elements the participant took over.
        kinds: Element type of every element (``load``, ``sgen``, ``storage``).
        power_kw: Power per step of every element, in kW.
        step_hours: Hours per step (power to energy).
        n_steps: Steps in the day.
    """
    generation = [0.0] * n_steps
    demand = [0.0] * n_steps
    for e in owns:
        kind = kinds.get(e)
        if kind == "storage":
            continue
        target = generation if kind == "sgen" else demand
        for t, kw in enumerate(list(power_kw.get(e, []))[:n_steps]):
            target[t] += kw * step_hours
    return generation, demand


# --------------------------------------------------------------------------------------
# The participant
# --------------------------------------------------------------------------------------
class Participant:
    """One prosumer at one bus during a market day.

    Args:
        id: Participant ID.
        bus: The bus it sits on.
        owns: The network elements it took over.
        generation_kwh: G_t, its generation per step.
        demand_kwh: D_t, its demand per step.
        battery: Its battery (``None``: none).
        initial_reputation: Reputation at the start of the day ([P1] eq. 12).
    """

    def __init__(
        self,
        id: str,
        bus: str,
        owns: Sequence[str],
        generation_kwh: Sequence[float],
        demand_kwh: Sequence[float],
        battery: Optional[Battery],
        initial_reputation: float = 0.5,
    ) -> None:
        if len(generation_kwh) != len(demand_kwh):
            raise ValueError(
                f"{id}: {len(generation_kwh)} generation steps, "
                f"{len(demand_kwh)} demand steps"
            )
        self.id = id
        self.bus = bus
        self.owns = list(owns)
        self.generation_kwh = list(generation_kwh)
        self.demand_kwh = list(demand_kwh)
        self.battery = battery
        self.initial_reputation = initial_reputation
        self.profit = 0.0
        self.reputation = initial_reputation
        self.reset()

    def reset(self) -> None:
        """Back to the start of the day: battery, profit, reputation."""
        if self.battery is not None:
            self.battery.reset()
        self.profit = 0.0
        self.reputation = self.initial_reputation

    # --- Position and feasibility (eq. 15) -------------------------------------------
    def net_kwh(self, step: int) -> float:
        """G_t − D_t: + surplus, − deficit."""
        return self.generation_kwh[step] - self.demand_kwh[step]

    def battery_room(self) -> tuple[float, float]:
        """(chargeable, dischargeable) energy at the bus this step (eq. 15c-d);
        none without a battery."""
        b = self.battery
        return (b.chargeable_kwh, b.dischargeable_kwh) if b else (0.0, 0.0)

    def max_sell_kwh(self, step: int) -> float:
        """Eq. 15a: q_sell,max = max(0, G_t − D_t) + E_dischargeable."""
        return max(0.0, self.net_kwh(step)) + self.battery_room()[1]

    def max_buy_kwh(self, step: int) -> float:
        """Eq. 15b: q_buy,max = max(0, D_t − G_t) + E_chargeable."""
        return max(0.0, -self.net_kwh(step)) + self.battery_room()[0]

    # --- Partner choice --------------------------------------------------------------
    def choose_partner(
        self,
        candidates: Sequence[str],
        distance_km: Callable[[str], float],
        reputation: Mapping[str, float],
        reputation_weight: float,
    ) -> Optional[str]:
        """The rule-based preferred partner ([P1] §3.4, phase 2 of §3.9): the
        candidate with the best weighted score of high reputation (eq. 12) and
        short grid distance d_ij (§3.5.1). Both are rescaled over the candidates
        so the weight means the same for each: closeness runs from 1 for the
        nearest candidate to 0 for the farthest, standing from 1 for the highest
        reputation to 0 for the lowest. Ties go to the nearer one. ``None`` when
        there is no candidate.

        Args:
            candidates: Participants it could name.
            distance_km: Grid distance from this participant to a candidate.
            reputation: Each candidate's reputation.
            reputation_weight: Weight of reputation against closeness, 0 to 1.
        """
        others = [c for c in candidates if c != self.id]
        if not others:
            return None
        km = {c: distance_km(c) for c in others}
        near, far = min(km.values()), max(km.values())

        rep = {c: reputation.get(c, 0.5) for c in others}
        low, high = min(rep.values()), max(rep.values())

        def score(c: str) -> tuple[float, float]:
            closeness = (far - km[c]) / (far - near) if far > near else 1.0
            standing = (rep[c] - low) / (high - low) if high > low else 1.0
            weighted = reputation_weight * standing
            return weighted + (1 - reputation_weight) * closeness, -km[c]

        return max(others, key=score)

    # --- Settlement (eq. 13, 14, 16) -------------------------------------------------
    def settle(self, step: int, trades: Sequence[Trade]) -> ParticipantOutcome:
        """Turn the step's trades into what the participant did and earned.

        After its trades it has ``G − D + bought − sold`` left at its bus (eq. 13):
        a surplus charges its battery, a deficit discharges it (eq. 16), and what
        the battery cannot take or give is exchanged with the upstream grid
        untraded. The step's trading profit adds to the running profit (eq. 14);
        the grid fees follow the step's power flow (``pay_fees``).
        """
        bought = sum(t.quantity for t in trades if t.buyer_id == self.id)
        sold = sum(t.quantity for t in trades if t.seller_id == self.id)
        # [P1] eq. 14: Σ (p_sell · q_sell − p_buy · q_buy); the fees come later
        profit = sum(t.price * t.quantity for t in trades if t.seller_id == self.id)
        profit -= sum(t.price * t.quantity for t in trades if t.buyer_id == self.id)
        g, d = self.generation_kwh[step], self.demand_kwh[step]
        balance = (g - d) + (bought - sold)  # [P1] eq. 13
        b = self.battery
        # [P1] eq. 16: a surplus charges the battery, a deficit discharges it
        charge = b.charge(balance) if b and balance > 0 else 0.0
        discharge = b.discharge(-balance) if b and balance < 0 else 0.0
        self.profit += profit  # profit_{t+1} = profit_t + ... ([P1] eq. 14)
        return ParticipantOutcome(
            participant_id=self.id,
            generation_kwh=g,
            demand_kwh=d,
            bought_kwh=bought,
            sold_kwh=sold,
            charge_kwh=charge,
            discharge_kwh=discharge,
            external_kwh=balance - charge + discharge,
            soc_kwh=b.energy_kwh if b else None,
            balance_kwh=balance,
            fees=0.0,
            profit=profit,
        )

    def pay_fees(
        self, outcome: ParticipantOutcome, trades: Sequence[Trade]
    ) -> ParticipantOutcome:
        """Its share of the step's grid fees (eq. 8), known once the step's power
        flow has run: taken from the running profit (eq. 14) and from the step's
        ``outcome``, which ``settle`` returned without fees."""
        fees = sum(t.buyer_fee for t in trades if t.buyer_id == self.id)
        fees += sum(t.seller_fee for t in trades if t.seller_id == self.id)
        self.profit -= fees
        return replace(outcome, fees=fees, profit=outcome.profit - fees)

    # --- Its power at the bus --------------------------------------------------------
    def injection(
        self, outcome: ParticipantOutcome, step_hours: float
    ) -> ParticipantInjection:
        """Its net power at its bus for the power flow, from what it physically
        did (never from its trades): generation and discharge flow in, demand and
        charge flow out. Replaces the trade-path flows of [P1] §3.5.3."""
        production = (outcome.generation_kwh + outcome.discharge_kwh) / step_hours
        consumption = (outcome.demand_kwh + outcome.charge_kwh) / step_hours
        return ParticipantInjection(
            self.id, self.bus, production, consumption, production - consumption
        )
