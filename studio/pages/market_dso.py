"""Market & DSO: how orders are priced and matched, how participants bid, and the
DSO's tariffs.

Writes ``scenario.market`` and ``scenario.dso`` (saved on every change). Grid fees
are not charged by the rebuilt market yet, so they are not offered here.
"""

from __future__ import annotations

from nicegui import ui

from core.market.clearing_price import DESCRIPTIONS
from studio.components.cards import section
from studio.components.labels import MECHANISMS
from studio.layout import shell
from studio.state import services


# --------------------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------------------
def page() -> None:
    """Clearing, bidding and the DSO, one card each."""
    with shell(
        "market",
        "Market & DSO",
        "How orders are matched and priced, how participants bid, and what the DSO "
        "pays and charges. Saved on every change; press Reset on the Step page to "
        "play with new settings.",
    ):
        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            with section(
                "Clearing",
                "Three stages: preferences, double auction, DSO",
                "gavel",
                classes="grow basis-0",
            ):
                _clearing()
            with section(
                "Bidding",
                "The rule that writes each participant's order",
                "sell",
                classes="grow basis-0",
            ):
                _bidding()
            with section(
                "DSO",
                "Buys what is left over, sells what is missing",
                "account_balance",
                classes="grow basis-0",
            ):
                _dso()


def _saver(section_name: str):
    """A function that sets one field of ``scenario.<section_name>`` and saves."""
    s = services()

    def save(field: str, value) -> None:
        if value is None:
            return
        setattr(getattr(s.scenario.current(), section_name), field, value)
        s.scenario.save()

    return save


# --------------------------------------------------------------------------------------
# Clearing
# --------------------------------------------------------------------------------------
def _clearing() -> None:
    m = services().scenario.current().market
    save = _saver("market")

    def mechanism(e) -> None:
        save("mechanism", e.value)
        caption.set_text(DESCRIPTIONS[e.value])

    ui.select(
        MECHANISMS,
        value=m.mechanism,
        label="Price of a peer-to-peer trade",
        on_change=mechanism,
    ).classes("w-full")
    caption = ui.label(DESCRIPTIONS[m.mechanism]).classes("mls-card-caption")

    for pair in (
        (("min_price", "Min price", 0.01), ("max_price", "Max price", 0.01)),
        (
            ("min_quantity", "Min quantity (kWh)", 0.1),
            ("max_quantity", "Max quantity (kWh)", 1),
        ),
    ):
        with ui.row().classes("w-full gap-2 no-wrap"):
            for field, label, step in pair:
                ui.number(
                    label,
                    value=getattr(m, field),
                    step=step,
                    on_change=lambda e, f=field: save(f, float(e.value or 0)),
                ).classes("grow basis-0")

    ui.label(
        "Orders are clipped to these bounds, and to what each participant can "
        "physically deliver or take (its surplus or deficit plus its battery)."
    ).classes("mls-card-caption")
    ui.switch(
        "Preferred partners",
        value=m.partner_preference,
        on_change=lambda e: save("partner_preference", bool(e.value)),
    )
    ui.label(
        "On: every participant names the electrically nearest participant on the "
        "other side as its partner; pairs that name each other trade in stage 1, "
        "before the auction. Off: stage 1 stays empty."
    ).classes("mls-card-caption")


# --------------------------------------------------------------------------------------
# Bidding
# --------------------------------------------------------------------------------------
def _bidding() -> None:
    m = services().scenario.current().market
    save = _saver("market")
    ui.label(
        "Each participant first charges or discharges its own battery, then sells "
        "what is left over or buys what is missing."
    ).classes("text-body2")

    def explain(margin: float) -> None:
        if margin < 0.5:
            text = "Bids lie above asks: peers trade with each other first."
        elif margin == 0.5:
            text = "Everyone bids the midpoint: trades happen only with jitter."
        else:
            text = "Asks lie above bids: no peer trades, everything goes to the DSO."
        hint.set_text(
            f"Sellers ask FiT + {margin:.2f} × spread, buyers bid utility − "
            f"{margin:.2f} × spread. {text}"
        )

    def margin(e) -> None:
        save("bid_margin", float(e.value))
        explain(float(e.value))

    ui.label("Margin").classes("text-caption")
    ui.slider(min=0, max=1, step=0.05, value=m.bid_margin, on_change=margin).props(
        "label"
    )
    hint = ui.label().classes("mls-card-caption")
    explain(m.bid_margin)
    ui.label("Jitter").classes("text-caption")
    ui.slider(
        min=0,
        max=0.5,
        step=0.05,
        value=m.bid_jitter,
        on_change=lambda e: save("bid_jitter", float(e.value)),
    ).props("label")
    ui.label(
        "Random spread of each price, as a share of the tariff spread, so the order "
        "book shows a range of prices."
    ).classes("mls-card-caption")
    ui.number(
        "Seed",
        value=m.seed,
        step=1,
        on_change=lambda e: save("seed", int(e.value or 0)),
    ).classes("w-full")


# --------------------------------------------------------------------------------------
# DSO
# --------------------------------------------------------------------------------------
def _dso() -> None:
    d = services().scenario.current().dso
    save = _saver("dso")
    ui.number(
        "Feed-in tariff (per kWh)",
        value=d.feed_in_tariff,
        step=0.01,
        on_change=lambda e: save("feed_in_tariff", float(e.value or 0)),
    ).classes("w-full")
    ui.label("What the DSO pays for every kWh it buys (stage 3).").classes(
        "mls-card-caption"
    )
    ui.number(
        "Utility price (per kWh)",
        value=d.utility_price,
        step=0.01,
        on_change=lambda e: save("utility_price", float(e.value or 0)),
    ).classes("w-full")
    ui.label("What the DSO charges for every kWh it sells (stage 3).").classes(
        "mls-card-caption"
    )
    ui.label(
        "Both are constant over the day for now. Local trading pays off between "
        "them: sellers get more than the feed-in tariff, buyers pay less than the "
        "utility price. Grid fees (paper eq. 8) are not charged yet."
    ).classes("mls-card-caption")
