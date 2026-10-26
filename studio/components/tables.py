"""Table helpers, and the trades of a market step (the Market step and Market probes
pages)."""

from typing import Any, Sequence

from nicegui import ui

from core.market.order import Trade

STAGE_LABELS = {1: "1 · Preferences", 2: "2 · Double auction", 3: "3 · DSO"}


def data_table(
    rows: list[dict[str, Any]],
    columns: list[tuple[str, str]] | None = None,
    row_key: str = "id",
    pagination: int = 10,
    badge_columns: dict[str, str] | None = None,
) -> ui.table:
    """Build a table. `columns` = [(field, label)]; `badge_columns` = {field: color_field}."""
    columns = columns or [
        (k, k.replace("_", " ")) for k in (rows[0].keys() if rows else [])
    ]
    table = (
        ui.table(
            columns=[
                {
                    "name": f,
                    "label": label,
                    "field": f,
                    "align": "left",
                    "sortable": True,
                }
                for f, label in columns
            ],
            rows=rows,
            row_key=row_key,
            pagination=pagination,
        )
        .classes("w-full")
        .props("flat dense")
    )

    # Badge columns show the value as a coloured chip; the colour comes from another
    # field of the same row (e.g. "state_color").
    for field, color_field in (badge_columns or {}).items():
        table.add_slot(
            f"body-cell-{field}",
            f'<q-td :props="props"><q-badge :color="props.row.{color_field}" :label="props.value" /></q-td>',
        )

    return table


def trades_table(trades: Sequence[Trade], fees: bool = False) -> None:
    """The trades of a step, one row each, and the peer and DSO volumes under them;
    with ``fees`` also each trade's grid fee (eq. 8) and who pays it."""
    if not trades:
        ui.label("No trades yet in this step.").classes("mls-card-caption")
        return

    rows = [
        {
            "n": n,
            "stage": STAGE_LABELS.get(t.stage, str(t.stage)),
            "seller": t.seller_id,
            "buyer": t.buyer_id,
            "kwh": round(t.quantity, 3),
            "price": round(t.price, 4),
            "value": round(t.quantity * t.price, 4),
            "km": round(t.distance, 3),
            "fee": round(t.fees, 4),
            "buyer_fee": round(t.buyer_fee, 4),
            "seller_fee": round(t.seller_fee, 4),
        }
        for n, t in enumerate(trades, start=1)
    ]
    columns = [
        ("stage", "Stage"),
        ("seller", "Seller"),
        ("buyer", "Buyer"),
        ("kwh", "kWh"),
        ("price", "Price"),
        ("value", "Value"),
    ]

    if fees:
        columns += [
            ("km", "Distance km"),
            ("fee", "Fee"),
            ("buyer_fee", "Buyer pays"),
            ("seller_fee", "Seller pays"),
        ]

    data_table(rows, columns, row_key="n", pagination=10)
    p2p = sum(t.quantity for t in trades if t.stage < 3)
    dso = sum(t.quantity for t in trades if t.stage == 3)
    ui.label(f"Peer to peer {p2p:.2f} kWh · with the DSO {dso:.2f} kWh").classes(
        "mls-card-caption"
    )
