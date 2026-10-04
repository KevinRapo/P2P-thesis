"""Market & DSO (05 §6): market rules, DSO tariffs and fees, environment settings.

Writes the draft's ``market``, ``dso`` and ``environment`` sections and
``grid.assessment.mode`` (02 §3.5–§3.7). Values shown are the draft's, else the
defaults; "Apply to draft" writes only what the user changed.
"""

from typing import Any

from nicegui import ui

from src_thesis.application.models import ExperimentFile
from src_thesis.studio.components.cards import section
from src_thesis.studio.components.charts import line_figure
from src_thesis.studio.forms import DraftForm
from src_thesis.studio.layout import shell
from src_thesis.studio.state import current_draft, services

_MECHANISMS = {
    "average": "Average of bid and ask",
    "buyer": "Buyer's price",
    "seller": "Seller's price",
    "bid_ask_spread": "Bid-ask spread",
    "nash_bargaining": "Nash bargaining",
    "proportional_surplus": "Proportional surplus",
}
# Weight groups of the reward (eq. 4–6, penalties) and the reputation (eq. 12):
# (path, title, what they weigh).
_WEIGHTS = [
    (
        "environment.reward.base_weights",
        "Base reward (eq. 4)",
        "Importance of each part of R_base",
    ),
    (
        "environment.reward.cooperation_weights",
        "Cooperation (eq. 5)",
        "Market-wide indicators; the original sums to 56",
    ),
    (
        "environment.reward.penalties",
        "Penalties",
        "Factors of the penalty terms",
    ),
    (
        "environment.reward.contribution_weights",
        "Contribution (eq. 6)",
        "Grid, price and local-trading contribution",
    ),
    (
        "environment.reputation.weights",
        "Reputation (eq. 12)",
        "Reliability, fairness and grid behaviour",
    ),
]


@ui.page("/build/market")
def market_page() -> None:
    """Market & DSO (05 §6): edit the market rules, DSO tariffs and fees, and the
    observation, reward and reputation settings of the draft.
    """
    s = services()
    draft = current_draft()
    resolved = s.config.resolve(draft)
    m, d, env = resolved.market, resolved.dso, resolved.environment
    # Every control passed to bind() or track() is saved by "Apply to draft" (only
    # those the user changed).
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
                            "Price min", value=m.get("price", {}).get("min")
                        ).classes("grow"),
                        float,
                    )
                    bind(
                        "market.price.max",
                        ui.number(
                            "Price max", value=m.get("price", {}).get("max")
                        ).classes("grow"),
                        float,
                    )
                with ui.row().classes("no-wrap gap-2 w-full"):
                    bind(
                        "market.quantity.min",
                        ui.number(
                            "Quantity min (kWh)",
                            value=m.get("quantity", {}).get("min"),
                        ).classes("grow"),
                        float,
                    )
                    bind(
                        "market.quantity.max",
                        ui.number(
                            "Quantity max (kWh)",
                            value=m.get("quantity", {}).get("max"),
                        ).classes("grow"),
                        float,
                    )
                ui.label(
                    "Bounds of every order: price per kWh and kWh per step. The "
                    "papers use 20–600 and 0–180."
                ).classes("mls-card-caption")
                bind(
                    "market.match_threshold",
                    ui.number(
                        "Smallest matched quantity (kWh)",
                        value=m.get("match_threshold"),
                        format="%.0e",
                    ).classes("w-full"),
                    float,
                )
                bind(
                    "market.partner_preference",
                    ui.switch(
                        "Agents choose trading partners (RL)",
                        value=m.get("partner_preference", False),
                    ),
                )
                bind(
                    "market.async_orders",
                    ui.switch(
                        "Asynchronous orders (random times within a step)",
                        value=m.get("async_orders", True),
                    ),
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
                            "Proof-of-work difficulty",
                            value=m.get("ledger", {}).get("difficulty"),
                            min=0,
                            step=1,
                        ).classes("grow"),
                        int,
                    )
                ui.label(
                    "Difficulty 0: a hash-chained log without mining (fast); each "
                    "step up multiplies the mining time."
                ).classes("mls-card-caption")

            with section(
                "DSO",
                "dso section (02 §3.6)",
                "account_balance",
                classes="grow basis-0",
            ):
                tariffs = d.get("tariffs", {})
                source = bind(
                    "dso.tariffs.source",
                    ui.toggle(
                        {"csv": "CSV", "synthetic": "Synthetic"},
                        value=tariffs.get("source", "synthetic"),
                    ).props("no-caps dense"),
                )
                source_hint = ui.label().classes("mls-card-caption")
                files = s.profiles.tariff_files()
                with ui.column().classes("w-full gap-1") as csv_box:
                    for key, label in (("feed_in", "Feed-in"), ("utility", "Utility")):
                        _tariff_csv(form, key, label, tariffs.get(key), files)
                bind(
                    "dso.tariffs.mode",
                    ui.select(
                        {
                            "normalized": "Normalised into the price bounds",
                            "absolute": "Absolute values",
                        },
                        value=tariffs.get("mode", "normalized"),
                        label="Tariff mapping",
                    ).classes("w-full"),
                )
                bind(
                    "dso.tariffs.reset_per_episode",
                    ui.switch(
                        "New tariff profiles every episode",
                        value=tariffs.get("reset_per_episode", False),
                    ),
                )
                fees = d.get("fees", {})
                bind(
                    "dso.fees.charged",
                    ui.switch(
                        "Fees are charged (I-28)", value=fees.get("charged", False)
                    ),
                )
                with ui.expansion("Fee factors and thresholds", icon="tune").classes(
                    "w-full"
                ):
                    ui.label(
                        "Eq. 8: congestion, transmission (distance), voltage, "
                        "imbalance and same-zone fees."
                    ).classes("mls-card-caption")
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
                rep = env.get("reputation", {})
                bind(
                    "environment.observation.version",
                    ui.select(
                        {
                            "v1": "v1: [P1] Table 2 (42 values)",
                            "v2-grid": "v2-grid: v1 + grid block",
                        },
                        value=obs.get("version", "v1"),
                        label="Observation version",
                    ).classes("w-full"),
                )
                with ui.row().classes("no-wrap gap-2 w-full"):
                    bind(
                        "environment.observation.forecast_error",
                        ui.number(
                            "Forecast error",
                            value=obs.get("forecast_error"),
                            step=0.05,
                            min=0,
                        ).classes("grow"),
                        float,
                    )
                    bind(
                        "environment.observation.forecast_anchors",
                        ui.number(
                            "Forecast anchors",
                            value=obs.get("forecast_anchors"),
                            min=1,
                            step=1,
                        ).classes("grow"),
                        int,
                    )
                bind(
                    "environment.observation.own_bus_voltage",
                    ui.select(
                        {
                            "private": "Own bus voltage: private",
                            "public": "Own bus voltage: public",
                            "off": "Own bus voltage: off",
                        },
                        value=obs.get("own_bus_voltage", "private"),
                        label="Grid observation",
                    ).classes("w-full"),
                )
                bind(
                    "environment.observation.include_partner_reputation",
                    ui.switch(
                        "Observe partners' reputation",
                        value=obs.get(
                            "include_partner_reputation",
                            m.get("partner_preference", False),
                        ),
                    ),
                )
                ui.separator()
                with ui.row().classes("no-wrap gap-2 w-full"):
                    bind(
                        "environment.reward.version",
                        ui.select(
                            ["corrected-v1"],
                            value=rew.get("version", "corrected-v1"),
                            label="Reward version",
                        ).classes("grow"),
                    )
                    bind(
                        "environment.reward.log_scale",
                        ui.number(
                            "Log scale (eq. 3)", value=rew.get("log_scale"), min=0
                        ).classes("grow"),
                        float,
                    )
                ui.label(
                    "Runs with different reward versions are never compared directly."
                ).classes("mls-card-caption")
                violation = rew.get("grid_violation", {})
                bind(
                    "environment.reward.grid_violation.attribution",
                    ui.select(
                        {
                            "shared": "Shared by all agents",
                            "bus": "Bus-attributed",
                            "marginal": "Marginal contribution",
                        },
                        value=violation.get("attribution", "bus"),
                        label="Grid violations are charged to (D-11, open)",
                    ).classes("w-full"),
                )
                with ui.row().classes("no-wrap gap-2 w-full"):
                    for key, label in (
                        ("w_voltage", "w voltage"),
                        ("w_loading", "w loading"),
                        ("w_nonconvergence", "w non-conv."),
                    ):
                        bind(
                            f"environment.reward.grid_violation.{key}",
                            ui.number(label, value=violation.get(key)).classes("grow"),
                            float,
                        )
                bind(
                    "grid.assessment.mode",
                    ui.toggle(
                        {"shadow": "Shadow", "feedback": "Feedback"},
                        value=resolved.grid.get("assessment", {}).get(
                            "mode", "feedback"
                        ),
                    ).props("no-caps dense"),
                )
                ui.label(
                    "Shadow: the grid is assessed and recorded but does not affect "
                    "rewards. Feedback: violations enter the reward and observation."
                ).classes("mls-card-caption")
                with ui.row().classes("no-wrap gap-2 w-full"):
                    decay = bind(
                        "environment.reputation.decay",
                        ui.select(
                            {
                                "time_of_day": "Time of day (original)",
                                "constant": "Constant factor",
                            },
                            value=rep.get("decay", "time_of_day"),
                            label="Reputation decay",
                        ).classes("grow"),
                    )
                    decay_factor = bind(
                        "environment.reputation.decay_factor",
                        ui.number(
                            "Factor", value=rep.get("decay_factor"), step=0.01
                        ).classes("grow"),
                        float,
                    )

        with section(
            "Reward and reputation weights",
            "Pre-filled with the original values; change only what the study varies",
            "balance",
        ):
            with ui.row().classes("w-full gap-6 items-start no-wrap"):
                for path, title, caption in _WEIGHTS:
                    weights = _get(resolved, path)
                    with ui.column().classes("grow basis-0 min-w-0 gap-1"):
                        ui.label(title).classes("text-weight-medium")
                        ui.label(caption).classes("mls-card-caption")
                        for key, value in weights.items():
                            bind(
                                f"{path}.{key}",
                                ui.number(
                                    key.replace("_", " "), value=value, step=0.1
                                ).classes("w-full"),
                                float,
                            )

        with section(
            "Tariffs",
            "The tariff profiles the DSO starts from, as stored in the CSVs",
            "show_chart",
        ):
            tariff_hint = ui.label().classes("mls-card-caption")
            tariff_box = ui.column().classes("w-full")

        with ui.row().classes("justify-end w-full"):
            ui.button("Apply to draft", icon="save", on_click=form.apply).props(
                "unelevated"
            )

    def refresh() -> None:
        """Explain the choices and redraw the tariffs with the unsaved changes."""
        source_hint.set_text(
            "CSV: daily profiles from data/prices; no file = the original's "
            "fit_60min.csv and utility_60min.csv; no column = each episode picks "
            "one at random (the original)."
            if source.value == "csv"
            else "Synthetic: MARLEM's DSO generator draws new step-shaped tariffs "
            "within the price bounds."
        )
        csv_box.set_visibility(source.value == "csv")
        decay_factor.set_visibility(decay.value == "constant")
        tariff_box.clear()
        try:
            preview = s.config.update(draft, form.changes())
            series = s.profiles.tariffs(preview)
        except (ValueError, OSError) as e:
            tariff_hint.set_text(f"Cannot read the tariffs: {e}")
            return
        if not series.y:
            tariff_hint.set_text(
                "Synthetic tariffs are generated per episode: there is no fixed "
                "curve to show."
            )
            return
        tariff_hint.set_text(
            "Raw CSV values. With mapping 'normalised' the DSO scales them into the "
            "price bounds and adds random variation (±25–30 %) each episode."
        )
        with tariff_box:
            ui.plotly(line_figure(series, height=260)).classes("w-full")

    for control in form.elements:
        control.on_value_change(refresh)
    refresh()


def _tariff_csv(
    form: DraftForm,
    key: str,
    label: str,
    spec: dict | None,
    files: dict[str, list[str]],
) -> None:
    """File and column selects for one tariff, written as ``dso.tariffs.<key>``."""
    spec = spec or {}
    with ui.row().classes("no-wrap gap-2 w-full"):
        path = ui.select(
            files, value=spec.get("path"), label=f"{label} CSV", clearable=True
        ).classes("grow")
        path.set_options({p: p.removeprefix("data/prices/") for p in files})
        column = ui.select(
            files.get(spec.get("path") or "", []),
            value=spec.get("column"),
            label="Column",
            clearable=True,
        ).classes("w-32")

    def columns() -> None:
        options = files.get(path.value or "", [])
        column.set_options(
            options, value=column.value if column.value in options else None
        )

    path.on_value_change(columns)
    form.elements += [path, column]
    form.track(
        f"dso.tariffs.{key}",
        lambda: (
            {"path": path.value, **({"column": column.value} if column.value else {})}
            if path.value
            else None
        ),
    )


def _get(file: ExperimentFile, path: str) -> dict[str, Any]:
    """The dict at a dotted ``path`` of the file (empty if absent)."""
    node: Any = file.model_dump()
    for key in path.split("."):
        node = (node or {}).get(key, {})
    return node or {}
