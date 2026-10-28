"""Market probes: tiny scripted market cases whose outcome is known by hand.

Each probe (``core/market/probes.py``) plays four participants on a SimBench LV
network with scripted orders over five midday steps, once with the power flow and
once with the graph method, and checks the market against values worked out from
the profiles. The page shows, per probe, what it isolates, its orders and what a
correct market gives; the checks of each step (PASS/FAIL); and the step played
out: the trades of every stage with their fees, the participants and the DSO.

The probes are played when the page first asks for them (about 10 s) and kept
until *Play again*.
"""

from __future__ import annotations

from typing import Optional

from nicegui import run, ui

from core.market.probes import Check, ProbeRun
from studio.adapters.validation_service import ValidationService
from studio.components.cards import key_values, placeholder, section
from studio.components.tables import data_table, trades_table
from studio.layout import shell
from studio.state import services

METHODS = {"powerflow": "Power flow", "graph": "Graph model"}


# --------------------------------------------------------------------------------------
# Tables: the summary, the checks, the participants
# --------------------------------------------------------------------------------------
def _verdict(checks: list[Check]) -> str:
    passed = sum(c.ok for c in checks)
    return f"{'PASS' if passed == len(checks) else 'FAIL'} {passed}/{len(checks)}"


def _color(text: str) -> str:
    return "positive" if text.startswith("PASS") else "negative"


def _summary(runs: list[ProbeRun], service: ValidationService) -> None:
    rows = []

    for key in dict.fromkeys(r.probe.key for r in runs):
        own = {r.method: r for r in runs if r.probe.key == key}
        row = {"key": key, "title": next(iter(own.values())).probe.title}

        for method in METHODS:
            row[method] = _verdict(list(own[method].checks))
            row[f"{method}_color"] = _color(row[method])

        row["same"] = _verdict(service.same_market(key))
        row["same_color"] = _color(row["same"])
        rows.append(row)

    data_table(
        rows,
        [
            ("key", "Probe"),
            ("title", "Shows"),
            ("powerflow", "Power flow"),
            ("graph", "Graph model"),
            ("same", "Same market on both"),
        ],
        row_key="key",
        badge_columns={m: f"{m}_color" for m in (*METHODS, "same")},
    )
    ui.label(
        "Checks passed of all steps. Same market: the same trades (stage, seller, "
        "buyer, kWh, price) with either grid method; only the fees may differ."
    ).classes("mls-card-caption")


def _checks_table(checks: list[Check]) -> None:
    rows = [
        {
            "n": n,
            "name": c.name,
            "expected": round(c.expected, 6),
            "got": round(c.got, 6),
            "result": "PASS" if c.ok else "FAIL",
            "result_color": "positive" if c.ok else "negative",
        }
        for n, c in enumerate(checks)
    ]
    data_table(
        rows,
        [
            ("name", "Check"),
            ("expected", "Expected"),
            ("got", "Market"),
            ("result", "Result"),
        ],
        row_key="n",
        pagination=20,
        badge_columns={"result": "result_color"},
    )


def _people_table(record) -> None:
    """Each participant's step from the record: profiles, order, trades,
    settlement (eq. 13, 14) and fees."""
    orders = {o.agent_id: o for o in record.orders}
    rows = []

    for pid, out in record.participants.items():
        o = orders.get(pid)
        rows.append(
            {
                "id": pid,
                "gen": round(out.generation_kwh, 3),
                "dem": round(out.demand_kwh, 3),
                "order": (
                    f"{'buy' if o.is_buy else 'sell'} {o.quantity:.3f} @ {o.price:.3f}"
                    + (f" → {o.partner_id}" if o.partner_id else "")
                    if o
                    else "—"
                ),
                "bought": round(out.bought_kwh, 3),
                "sold": round(out.sold_kwh, 3),
                "balance": round(out.balance_kwh, 3),
                "external": round(out.external_kwh, 3),
                "fees": round(out.fees, 4),
                "profit": round(out.profit, 4),
            }
        )

    data_table(
        rows,
        [
            ("id", "Participant"),
            ("gen", "Generation kWh"),
            ("dem", "Demand kWh"),
            ("order", "Order (→ partner named)"),
            ("bought", "Bought"),
            ("sold", "Sold"),
            ("balance", "Balance (eq. 13)"),
            ("external", "Untraded kWh"),
            ("fees", "Fees"),
            ("profit", "Step profit"),
        ],
    )
    ui.label(
        "Balance = G − D + bought − sold; untraded is what no trade covered (0 when "
        "the orders match the profiles). Profit = sales − purchases − fees (eq. 14)."
    ).classes("mls-card-caption")


# --------------------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------------------
class ProbesView:
    """The summary of every probe, and one probe on one method, one step at a time.

    Args:
        service: The Validation service.
    """

    def __init__(self, service: ValidationService) -> None:
        self.service = service
        self.runs: list[ProbeRun] = []

        # Top line: Play again button | status note
        with ui.row().classes("w-full items-center gap-3"):
            self.again = ui.button(
                "Play again", icon="replay", on_click=lambda: self.load(again=True)
            ).props("flat no-caps dense")
            self.note = ui.label().classes("mls-card-caption")

        # Card: the summary table of every probe (filled by load())
        with section("Every probe", "Played on both grid methods", "rule"):
            self.summary = ui.column().classes("w-full")

        # Selector row for the detail below: probe | grid method | step
        with ui.row().classes("w-full items-center gap-3"):
            self.probe = ui.select({}, label="Probe", on_change=self._draw).classes(
                "grow"
            )
            self.method = ui.radio(
                METHODS, value="powerflow", on_change=self._draw
            ).props("inline")
            self.step = ui.select({}, label="Step", on_change=self._draw).classes(
                "w-40"
            )

        # The selected probe's cards (filled by _draw())
        self.detail = ui.column().classes("w-full gap-4")

    async def load(self, again: bool = False) -> None:
        self.again.props("loading")
        self.note.set_text(
            "Playing the probes on both grid methods ..."
            if again or not self.service.played
            else ""
        )

        try:
            self.runs = await run.io_bound(self.service.market_probes, again)
        except Exception as e:  # noqa: BLE001  show the error on the page
            self.note.set_text(f"The probes failed to play: {e}")
            return
        finally:
            self.again.props(remove="loading")

        if not self.runs:  # the page was closed while they played
            return

        self.note.set_text(
            f"{len(self.runs)} runs: {sum(r.ok for r in self.runs)} pass every check"
        )
        self.summary.clear()

        with self.summary:
            _summary(self.runs, self.service)

        probes = {r.probe.key: f"{r.probe.key} · {r.probe.title}" for r in self.runs}
        self.probe.set_options(probes, value=self.probe.value or next(iter(probes)))
        steps = {r.step: f"{r.step:02d}:00" for r in self.runs[0].records}
        self.step.set_options(steps, value=self.step.value or next(iter(steps)))
        self._draw()

    def _run(self) -> Optional[ProbeRun]:
        for r in self.runs:
            if r.probe.key == self.probe.value and r.method == self.method.value:
                return r
        return None

    def _draw(self, _=None) -> None:
        found = self._run()
        self.detail.clear()

        record = next(
            (r for r in found.records if r.step == self.step.value) if found else (),
            None,
        )

        if record is None:  # the options are still being filled
            return

        p = found.probe
        checks = [c for c in found.checks if c.step == record.step]

        # The detail cards, top to bottom: the probe, its checks, trades,
        # participants, DSO and grid, validation notes
        with self.detail:
            with section(f"{p.key} · {p.title}", p.shows, "science"):
                key_values({"Orders": p.setup, "A correct market gives": p.expect})

            with section(
                f"Checks at {record.step:02d}:00",
                f"{METHODS[found.method]}: {_verdict(checks)}; the expected values "
                "are worked out from this step's profiles and tariffs",
                "fact_check",
            ):
                _checks_table(checks)

            with section(
                "Trades",
                "Every trade of the step by stage, with its grid fee (eq. 8; a "
                "negative fee is the same-zone bonus) and who pays it",
                "swap_horiz",
            ):
                trades_table(record.trades, fees=True)

            with section("Participants", icon="groups"):
                _people_table(record)

            with section("DSO and grid", icon="hub"):
                d, g = record.dso, record.grid
                shown = {
                    "DSO bought / sold kWh": f"{d.bought_kwh:.3f} / {d.sold_kwh:.3f}",
                    "DSO balance (eq. 7) kWh": f"{d.balance_kwh:.3f}",
                    "DSO energy revenue": f"{d.energy_revenue:.4f}",
                    "Fees collected": f"{d.fees:.4f}",
                    "Clearing price": f"{record.clearing_price:.4f}",
                    "Power flow: highest line loading %": (
                        f"{g.max_line_loading_percent:.2f}"
                    ),
                }

                if record.signal is not None:
                    shown["Graph model: highest line loading % (the fees')"] = (
                        f"{record.signal.max_line_loading_percent:.2f}"
                    )

                key_values(shown)

            if record.notes:
                with section("Validation notes", icon="info"):
                    for note in record.notes:
                        ui.label(note).classes("text-body2")


def page() -> None:
    """The probes, played when the page first opens."""
    with shell(
        "market_probes",
        "Market probes",
        "Tiny scripted market cases whose outcome is known by hand, played on both "
        "grid methods: each isolates one part of the market step.",
    ):
        view = ProbesView(services().validation)

        # A waiting note where the detail cards will appear
        if not services().validation.played:
            with view.detail:
                placeholder("Playing the probes ...", "hourglass_empty")

        ui.timer(0.05, view.load, once=True)
