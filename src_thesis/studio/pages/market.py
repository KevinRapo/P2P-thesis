"""Market & DSO (04 §4.4): market rules, DSO tariffs and fees, environment settings."""

from nicegui import ui

from ..components import line_figure, not_implemented, section
from ..layout import shell
from ..state import current_draft, services

_MECHANISMS = [
    "average",
    "buyer",
    "seller",
    "bid_ask_spread",
    "nash_bargaining",
    "proportional_surplus",
]


@ui.page("/build/market")
def market_page() -> None:
    s = services()
    draft = current_draft()
    m, d, env = draft.market, draft.dso, draft.environment
    with shell(
        "market",
        "Market & DSO",
        "Market rules, DSO tariffs and fees, observation and reward settings",
    ):
        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            with section(
                "Market",
                "market section (02 §3.5)",
                "storefront",
                classes="grow basis-0",
            ):
                ui.select(
                    _MECHANISMS,
                    value=m.get("mechanism", "average"),
                    label="Clearing mechanism",
                ).classes("w-full")
                with ui.row().classes("no-wrap gap-2 w-full"):
                    ui.number(
                        "Price min", value=m.get("price", {}).get("min", 20)
                    ).classes("grow")
                    ui.number(
                        "Price max", value=m.get("price", {}).get("max", 600)
                    ).classes("grow")
                with ui.row().classes("no-wrap gap-2 w-full"):
                    ui.number(
                        "Quantity min (kWh)", value=m.get("quantity", {}).get("min", 0)
                    ).classes("grow")
                    ui.number(
                        "Quantity max (kWh)",
                        value=m.get("quantity", {}).get("max", 180),
                    ).classes("grow")
                ui.switch(
                    "RL partner preference", value=m.get("partner_preference", False)
                )
                ui.switch("Asynchronous orders", value=m.get("async_orders", True))
                with ui.row().classes("no-wrap gap-2 w-full items-center"):
                    ui.switch("Ledger", value=m.get("ledger", {}).get("enabled", True))
                    ui.number(
                        "PoW difficulty", value=m.get("ledger", {}).get("difficulty", 0)
                    ).classes("grow")

            with section(
                "DSO",
                "dso section (02 §3.6)",
                "account_balance",
                classes="grow basis-0",
            ):
                tariffs = d.get("tariffs", {})
                ui.toggle(
                    {"csv": "CSV", "synthetic": "Synthetic"},
                    value=tariffs.get("source", "csv"),
                ).props("no-caps dense")
                ui.select(
                    ["normalized", "absolute"],
                    value=tariffs.get("mode", "normalized"),
                    label="Tariff mapping",
                ).classes("w-full")
                fees = d.get("fees", {})
                ui.switch("Fees are charged", value=fees.get("charged", True))
                with ui.expansion("Fee factors and thresholds", icon="tune").classes(
                    "w-full"
                ):
                    with ui.grid(columns=2).classes("w-full gap-2"):
                        for key, value in fees.items():
                            if key != "charged":
                                ui.number(key.replace("_", " "), value=value, step=0.05)

            with section(
                "Environment",
                "environment section (02 §3.7)",
                "psychology",
                classes="grow basis-0",
            ):
                obs, rew = env.get("observation", {}), env.get("reward", {})
                ui.select(
                    ["v1", "v2-grid"],
                    value=obs.get("version", "v2-grid"),
                    label="Observation version",
                ).classes("w-full")
                ui.select(
                    ["corrected-v1"],
                    value=rew.get("version", "corrected-v1"),
                    label="Reward version",
                ).classes("w-full")
                ui.toggle(
                    {"shadow": "Shadow", "feedback": "Feedback"},
                    value=draft.grid.get("assessment", {}).get("mode", "feedback"),
                ).props("no-caps dense")
                ui.number(
                    "Forecast error", value=obs.get("forecast_error", 0.3), step=0.05
                ).classes("w-full")
                ui.select(
                    {
                        "shared": "Shared",
                        "bus": "Bus-attributed",
                        "marginal": "Marginal",
                    },
                    value=rew.get("grid_violation", {}).get("attribution", "bus"),
                    label="Violation attribution (D-11, open)",
                ).classes("w-full")
                with ui.expansion(
                    "Reward and reputation weights", icon="balance"
                ).classes("w-full"):
                    ui.label("Weights of eq. 4–6 and eq. 12 (02 §3.7).").classes(
                        "mls-card-caption"
                    )
                    ui.button(
                        "Edit weights",
                        icon="edit",
                        on_click=lambda: not_implemented("Edit weights"),
                    ).props("flat")

        with section(
            "Tariffs over the time window",
            "Feed-in tariff and utility price",
            "show_chart",
        ):
            ui.plotly(line_figure(s.profiles.tariffs(draft), height=260)).classes(
                "w-full"
            )

        with ui.row().classes("justify-end w-full"):
            ui.button(
                "Apply to draft",
                icon="save",
                on_click=lambda: not_implemented("Apply market settings"),
            ).props("unelevated")
