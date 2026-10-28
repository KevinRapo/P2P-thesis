"""RL probes: for a probe run, what the probe is and what it scored.

The runs are picked in the same table as on the Results page
(``studio/components/run_table.py``), with two more columns for a probe run: its
probe and its result. For the ticked probe runs, a summary (probe × paradigm, each
run's result: PASS or FAIL with its worst error over its tolerance, or 8b's share
of coordinating pairs), then one probe run at a time: what the probe tests, its
setup, the exact answer, what a correct learner shows, the market feature it
stands for (``core/runner/probe_runs.py``), and its checks (``checks.csv``:
expected against what the trained networks give). A run is scored by
``probe_check.score_to_file``. How any run's learner behaved is on Results →
Learning.
"""

from __future__ import annotations

from nicegui import run, ui

from core.runner.probe_runs import ProbeRunInfo
from studio.adapters.results_service import ResultsService
from studio.adapters.validation_service import ValidationService
from studio.components.cards import key_values, placeholder, section
from studio.components.run_table import RUN_COLUMNS, RunTable, labels_of
from studio.components.tables import data_table
from studio.layout import shell
from studio.state import services

SHOW_TESTS = "rl_probes_show_tests"  # app.storage.user key
# The run table's columns: what the run was, its probe and result, its state.
COLUMNS = RUN_COLUMNS[:7] + [("probe", "Probe"), ("result", "Result"), RUN_COLUMNS[7]]


# --------------------------------------------------------------------------------------
# The probes: a summary of the ticked probe runs, one run's probe and checks
# --------------------------------------------------------------------------------------
def _result_text(info: ProbeRunInfo) -> str:
    """``PASS 0.42``, ``FAIL 2.66``, ``share 0.50`` (8b), or ``not scored``."""
    if info.result is None:
        return "not scored"

    if info.result == "MEASURED":
        return f"share {info.worst:.2f}"

    return f"{info.result} {info.worst:.2f}"


def _probe_order(probe: str) -> tuple[int, str]:
    return int(probe.rstrip("ab")), probe


def _summary(found: dict[str, ProbeRunInfo]) -> None:
    """Probe × paradigm: every ticked run's result, by seed (and budget scale)."""
    cells: dict[tuple[str, str], list[tuple[float, int, str]]] = {}
    names = {}

    for info in found.values():
        tag = f"s{info.seed}" + ("" if info.scale == 1 else f" ×{info.scale:g}")
        cells.setdefault((info.probe, info.paradigm), []).append(
            (info.scale, info.seed, f"{_result_text(info)} ({tag})")
        )
        names[info.probe] = info.about.name if info.about else ""

    paradigms = sorted({p for _, p in cells})
    rows = [
        {"probe": f"{probe} · {names[probe]}"}
        | {
            p: " · ".join(text for *_, text in sorted(cells.get((probe, p), [])))
            for p in paradigms
        }
        for probe in sorted(names, key=_probe_order)
    ]
    data_table(
        rows,
        [("probe", "Probe")] + [(p, p.upper()) for p in paradigms],
        row_key="probe",
        pagination=15,
    )
    ui.label(
        "PASS or FAIL with the worst error over its tolerance (above 1 fails; inf: "
        "a wrong category); 8b: the share of pairs that coordinate (measured, not "
        "judged). ×2, ×4: an escalated run with that many times the budget."
    ).classes("mls-card-caption")


def _probe_card(label: str, info: ProbeRunInfo) -> None:
    about = info.about

    # One card: what the probe tests, then its check table and a note
    with section(
        f"Probe {info.probe}" + (f" · {about.name}" if about else ""),
        f"{label}: {info.paradigm.upper()}, seed {info.seed}"
        + ("" if info.scale == 1 else f", ×{info.scale:g} budget")
        + f" · {_result_text(info)}",
        "science",
    ):
        if about:
            key_values(
                {
                    "Tests": about.tests,
                    "Setup": about.setup,
                    "Exact answer": about.answer,
                    "A correct learner": about.expect,
                    "In the market": about.market,
                }
            )

        if info.checks is None:
            ui.label(
                "Not scored yet: probe_check.score_to_file writes its checks."
            ).classes("mls-card-caption")
            return

        rows = [
            {
                "n": n,
                "state": row.state,
                "output": row.output,
                "expected": round(float(row.expected), 4),
                "got": round(float(row.got), 4),
                "tolerance": round(float(row.tolerance), 4),
                "result": "PASS" if bool(row.ok) else "FAIL",
                "result_color": "positive" if bool(row.ok) else "negative",
            }
            for n, row in enumerate(info.checks.itertuples())
        ]
        data_table(
            rows,
            [
                ("state", "State"),
                ("output", "Output"),
                ("expected", "Expected"),
                ("got", "Trained network"),
                ("tolerance", "Tolerance"),
                ("result", "Result"),
            ],
            row_key="n",
            pagination=15,
            badge_columns={"result": "result_color"},
        )
        ui.label(
            "Read from the trained networks in the probe's check states, not from "
            "the return. A tolerance of 0 is a category, which must be exact."
        ).classes("mls-card-caption")


# --------------------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------------------
class ProbesView:
    """The run table and the ticked probe runs.

    Args:
        service: The Results service.
        validation: The Validation service (the probe runs' probe and score).
    """

    def __init__(self, service: ResultsService, validation: ValidationService) -> None:
        self.service = service
        self.validation = validation
        self._drawn = 0  # the latest draw

        # The run table at the top, with a tick box per run
        self.table = RunTable(
            service,
            self._selected,
            SHOW_TESTS,
            columns=COLUMNS,
            read=validation.rl_overview,
        )

        # The ticked probe runs, drawn by _show_probes()
        self.probes = ui.column().classes("w-full gap-4")

    async def load(self) -> None:
        await self.table.load()
        await self._selected()  # the placeholders

    @property
    def selected(self) -> list[str]:
        return self.table.selected

    async def _selected(self) -> None:
        await self._show_probes()

    # --- Probes: the ticked probe runs ------------------------------------------------
    async def _show_probes(self) -> None:
        keys = list(self.selected)
        self._drawn += 1
        draw = self._drawn
        self.probes.clear()
        found = await run.io_bound(self.validation.probe_runs, keys)

        if draw != self._drawn:  # ticked again meanwhile
            return

        # The Probes tab, top to bottom: summary card, probe-run picker, that run's
        # probe card
        with self.probes:
            if not found:
                placeholder(
                    "Tick probe runs in the table (an experiment probes_<preset>) to "
                    "see their probes and checks; any run's learner is on Results → "
                    "Learning.",
                    "science",
                )
                return

            labels = labels_of(list(found))

            with section(
                "The ticked probe runs",
                f"{len(found)} of {len(keys)} ticked runs are probe runs",
                "grid_view",
            ):
                _summary(found)

            order = sorted(
                found,
                key=lambda k: (
                    _probe_order(found[k].probe),
                    found[k].paradigm,
                    found[k].seed,
                    found[k].scale,
                ),
            )
            options = {k: f"{labels[k]} · {_result_text(found[k])}" for k in order}
            chosen = ui.select(options, value=order[0], label="Probe run").classes(
                "w-full"
            )
            # The chosen run's probe card, redrawn by show()
            card = ui.column().classes("w-full")

            def show() -> None:
                card.clear()

                with card:
                    _probe_card(labels[chosen.value], found[chosen.value])

            chosen.on_value_change(lambda _: show())
            show()


def page() -> None:
    """The runs, read once when the page opens."""
    s = services()

    with shell(
        "rl_probes",
        "RL probes",
        "The RL probes' runs: what each probe is and what it scored. Runs of the "
        "clusters after Sync results on the Runs page; how a run learned is on "
        "Results → Learning.",
    ):
        view = ProbesView(s.results, s.validation)
        ui.timer(0.05, view.load, once=True)
