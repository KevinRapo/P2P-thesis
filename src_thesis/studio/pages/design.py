"""Design (04 §4.6): the learning plan, i.e. the `learning` section of the file."""

from nicegui import ui

from src_thesis.studio.components.cards import not_implemented, section, stat, stat_grid
from src_thesis.studio.layout import shell
from src_thesis.studio.state import current_draft, services

PARADIGMS = ["ctce", "ctde", "dtde"]
ALGORITHMS = ["ppo", "appo", "sac"]


@ui.page("/experiment/design")
def design_page() -> None:
    """Design (04 §4.6): the draft's learning plan (matrix, seeds, budget,
    hyperparameters, sweep). Read-only for now.
    """
    s = services()
    draft = current_draft()
    learning = draft.learning
    with shell(
        "design",
        "Design",
        "Paradigms × algorithms, hyperparameters, tuning, budget, evaluation",
    ):
        # Placeholder page: every control shows the draft's learning plan, but nothing
        # is saved yet ("Apply to draft" is not wired). The run count and time estimate
        # come from the demo ExperimentService.
        estimate = s.experiments.estimate(draft)
        with stat_grid():
            stat(
                "Runs",
                str(estimate.runs),
                "including seeds and sweep points",
                "play_circle",
            )
            stat(
                "Estimated time",
                f"{estimate.estimated_hours} h",
                estimate.note,
                "schedule",
            )
            stat(
                "Budget",
                f"{learning.get('budget', {}).get('value', 0):,}",
                learning.get("budget", {}).get("unit", ""),
                "speed",
            )

        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            with section(
                "Matrix",
                "Tick the cells to run (default 3 × 3)",
                "grid_on",
                classes="basis-1/3 min-w-0",
            ):
                with ui.grid(columns=4).classes("items-center gap-2"):
                    ui.label("")
                    for a in ALGORITHMS:
                        ui.label(a.upper()).classes("text-weight-bold text-center")
                    for p in PARADIGMS:
                        ui.label(p.upper()).classes("text-weight-bold")
                        for a in ALGORITHMS:
                            ui.checkbox(
                                value=p in learning.get("paradigms", [])
                                and a in learning.get("algorithms", [])
                            )
                ui.separator()
                ui.input(
                    "Seeds", value=", ".join(str(x) for x in learning.get("seeds", []))
                ).classes("w-full")
                with ui.row().classes("no-wrap gap-2 w-full"):
                    ui.select(
                        ["env_steps", "iterations", "episodes"],
                        value=learning.get("budget", {}).get("unit"),
                        label="Budget unit",
                    ).classes("grow")
                    ui.number(
                        "Budget", value=learning.get("budget", {}).get("value")
                    ).classes("grow")

            with section(
                "Algorithm parameters",
                "Pre-filled with the original MARLEM defaults (02 §3.8)",
                "tune",
                classes="grow basis-0",
            ):
                # One tab per algorithm, one control per hyperparameter, chosen by the
                # value's type.
                params = learning.get("algorithm_params", {})
                with ui.tabs().classes("w-full") as tabs:
                    for a in ALGORITHMS:
                        ui.tab(a, label=a.upper())
                with ui.tab_panels(tabs, value=ALGORITHMS[0]).classes("w-full"):
                    for a in ALGORITHMS:
                        with ui.tab_panel(a):
                            with ui.grid(columns=3).classes("w-full gap-2"):
                                for key, value in params.get(a, {}).items():
                                    if isinstance(value, bool):
                                        ui.switch(key, value=value)
                                    elif isinstance(value, (int, float)):
                                        ui.number(key, value=value, format="%.6g")
                                    elif isinstance(value, dict):
                                        for sub, sub_value in value.items():
                                            ui.number(f"{key}.{sub}", value=sub_value)
                                    else:
                                        ui.input(key, value=str(value))

        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            with section("Paradigm options", icon="hub", classes="grow basis-0"):
                options = learning.get("paradigm_options", {})
                for p in ["ctce", "ctde"]:
                    ui.select(
                        ["sum", "mean"],
                        value=options.get(p, {}).get("reward_aggregation", "sum"),
                        label=f"{p.upper()} reward aggregation",
                    ).classes("w-full")
                ui.number(
                    "Embeddings dim (CTCE/CTDE)",
                    value=learning.get("model", {}).get("embeddings_dim", 128),
                ).classes("w-full")
            with section(
                "Tuning",
                "Population Based Training",
                "auto_graph",
                classes="grow basis-0",
            ):
                tuning = learning.get("tuning", {})
                ui.toggle(
                    {"none": "None", "pbt": "PBT"}, value=tuning.get("method", "none")
                ).props("no-caps dense")
                ui.number(
                    "Population size", value=tuning.get("num_samples", 1)
                ).classes("w-full")
                ui.number(
                    "Perturbation interval",
                    value=learning.get("checkpoint", {}).get("every", 10),
                ).classes("w-full")
                ui.button(
                    "Edit mutation domains",
                    icon="edit",
                    on_click=lambda: not_implemented("Edit mutations"),
                ).props("flat")
            with section(
                "Evaluation and baselines", icon="fact_check", classes="grow basis-0"
            ):
                ev = draft.evaluation
                with ui.row().classes("no-wrap gap-2 w-full"):
                    ui.number(
                        "Every (iterations)", value=ev.get("interval", 10)
                    ).classes("grow")
                    ui.number("Episodes", value=ev.get("episodes", 20)).classes("grow")
                ui.select(
                    ["holdout", "train"],
                    value=ev.get("days", "holdout"),
                    label="Evaluation days",
                ).classes("w-full")
                for baseline in ["no_order", "random", "rule_based"]:
                    ui.checkbox(
                        baseline.replace("_", "-"), value=baseline in draft.baselines
                    )
            with section("Sweep and resources", icon="dns", classes="grow basis-0"):
                sweep = draft.sweep.get("parameters", {})
                ui.label(
                    ", ".join(f"{k} ({len(v)})" for k, v in sweep.items()) or "No sweep"
                ).classes("text-body2")
                ui.button(
                    "Edit sweep",
                    icon="edit",
                    on_click=lambda: not_implemented("Edit sweep"),
                ).props("flat")
                res = draft.resources
                with ui.row().classes("no-wrap gap-2 w-full"):
                    ui.number("CPUs / run", value=res.get("cpus_per_run", 6)).classes(
                        "grow"
                    )
                    ui.number(
                        "Parallel runs", value=res.get("max_parallel_runs", 1)
                    ).classes("grow")

        with ui.row().classes("justify-end w-full gap-2"):
            ui.button(
                "Apply to draft",
                icon="save",
                on_click=lambda: not_implemented("Apply learning plan"),
            ).props("outline")
            ui.button(
                "Continue to validation",
                icon="arrow_forward",
                on_click=lambda: ui.navigate.to("/experiment/validate"),
            ).props("unelevated")
