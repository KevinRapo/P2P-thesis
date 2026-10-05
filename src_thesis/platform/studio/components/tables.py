"""Table helpers."""

from typing import Any

from nicegui import ui

_STATE_COLORS = {
    "READY": "blue-grey",
    "QUEUED": "grey",
    "RUNNING": "info",
    "COMPLETED": "positive",
    "FAILED": "negative",
    "CANCELLING": "warning",
    "CANCELLED": "grey-7",
}


def state_color(state: str) -> str:
    """Badge colour for a run state (grey for unknown states)."""
    return _STATE_COLORS.get(state, "grey")


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
