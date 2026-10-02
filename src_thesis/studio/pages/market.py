"""Market & DSO (04 §4.4): market rules, DSO tariffs and fees, environment settings."""

from nicegui import ui

from ..components import line_figure, not_implemented, section
from ..forms import DraftForm
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
    """Market & DSO (04 §4.4): edit the market rules, DSO tariffs and fees, and the
    observation and reward settings of the draft.
    """
    s = services()
    draft = current_draft()
    m, d, env = draft.market, draft.dso, draft.environment
    form = DraftForm(draft)
    bind = form.bind
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
                bind(
                    "market.mechanism",
                    ui.select(
                        _MECHANISMS,
                        value=m.get("mechanism", "average"),
                        label="Clearing mechanism",
                    ).classes("w-full"),
                )
                with ui.row().classes("no-wrap gap-2 w-full"):
                    bind(
                        "market.price.min",
                        ui.number(
                            "Price min", value=m.get("price", {}).get("min", 20)
                        ).classes("grow"),
                        float,
                    )
                    bind(
                        "market.price.max",
                        ui.number(
                            "Price max", value=m.get("price", {}).get("max", 600)
                        ).classes("grow"),
                        float,
                    )
                with ui.row().classes("no-wrap gap-2 w-full"):
                    bind(
                        "market.quantity.min",
                        ui.number(
                            "Quantity min (kWh)",
                            value=m.get("quantity", {}).get("min", 0),
                        ).classes("grow"),
                        float,
                    )
                    bind(
                        "market.quantity.max",
                        ui.number(
                            "Quantity max (kWh)",
                            value=m.get("quantity", {}).get("max", 180),
                        ).classes("grow"),
                        float,
                    )
                bind(
                    "market.partner_preference",
                    ui.switch(
                        "RL partner preference",
                        value=m.get("partner_preference", False),
                    ),
                )
                bind(
                    "market.async_orders",
                    ui.switch("Asynchronous orders", value=m.get("async_orders", True)),
                )
                with ui.row().classes("no-wrap gap-2 w-full items-center"):
                    bind(
                        "market.ledger.enabled",
                        ui.switch(
                            "Ledger", value=m.get("ledger", {}).get("enabled", True)
                        ),
                    )
                    bind(
                        "market.ledger.difficulty",
                        ui.number(
                            "PoW difficulty",
                            value=m.get("ledger", {}).get("difficulty", 0),
                            min=0,
                            step=1,
                        ).classes("grow"),
                        int,
                    )

            with section(
                "DSO",
                "dso section (02 §3.6)",
                "account_balance",
                classes="grow basis-0",
            ):
                tariffs = d.get("tariffs", {})
                bind(
                    "dso.tariffs.source",
                    ui.toggle(
                        {"csv": "CSV", "synthetic": "Synthetic"},
                        value=tariffs.get("source", "csv"),
                    ).props("no-caps dense"),
                )
                bind(
                    "dso.tariffs.mode",
                    ui.select(
                        ["normalized", "absolute"],
                        value=tariffs.get("mode", "normalized"),
                        label="Tariff mapping",
                    ).classes("w-full"),
                )
                fees = d.get("fees", {})
                bind(
                    "dso.fees.charged",
                    ui.switch("Fees are charged", value=fees.get("charged", True)),
                )
                with ui.expansion("Fee factors and thresholds", icon="tune").classes(
                    "w-full"
                ):
                    with ui.grid(columns=2).classes("w-full gap-2"):
                        for key, value in fees.items():
                            if key != "charged":
                                bind(
                                    f"dso.fees.{key}",
                                    ui.number(
                                        key.replace("_", " "), value=value, step=0.05
                                    ),
                                    float,
                                )

            with section(
                "Environment",
                "environment section (02 §3.7)",
                "psychology",
                classes="grow basis-0",
            ):
                obs, rew = env.get("observation", {}), env.get("reward", {})
                bind(
                    "environment.observation.version",
                    ui.select(
                        ["v1", "v2-grid"],
                        value=obs.get("version", "v2-grid"),
                        label="Observation version",
                    ).classes("w-full"),
                )
                bind(
                    "environment.reward.version",
                    ui.select(
                        ["corrected-v1"],
                        value=rew.get("version", "corrected-v1"),
                        label="Reward version",
                    ).classes("w-full"),
                )
                bind(
                    "grid.assessment.mode",
                    ui.toggle(
                        {"shadow": "Shadow", "feedback": "Feedback"},
                        value=draft.grid.get("assessment", {}).get("mode", "feedback"),
                    ).props("no-caps dense"),
                )
                bind(
                    "environment.observation.forecast_error",
                    ui.number(
                        "Forecast error",
                        value=obs.get("forecast_error", 0.3),
                        step=0.05,
                    ).classes("w-full"),
                    float,
                )
                bind(
                    "environment.reward.grid_violation.attribution",
                    ui.select(
                        {
                            "shared": "Shared",
                            "bus": "Bus-attributed",
                            "marginal": "Marginal",
                        },
                        value=rew.get("grid_violation", {}).get("attribution", "bus"),
                        label="Violation attribution (D-11, open)",
                    ).classes("w-full"),
                )
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
            ui.button("Apply to draft", icon="save", on_click=form.apply).props(
                "unelevated"
            )
