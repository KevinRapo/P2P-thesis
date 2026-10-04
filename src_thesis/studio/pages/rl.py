"""RL (05 §6): the learning plan and how runs are evaluated, swept and resourced.

Writes the draft's ``learning``, ``evaluation``, ``baselines``, ``sweep``,
``resources`` and ``outputs`` sections (02 §3.8–§3.13). Values shown are the
draft's, else the defaults; "Apply to draft" writes only what the user changed.
The run count at the top follows the unsaved changes.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from nicegui import ui

from src_thesis.studio.components.cards import section, stat, stat_grid
from src_thesis.studio.forms import DraftForm
from src_thesis.studio.layout import shell
from src_thesis.studio.state import current_draft, services

PARADIGMS = {
    "ctce": "CTCE: one central policy acts for all agents",
    "ctde": "CTDE: central critic in training, own policies in execution",
    "dtde": "DTDE: every agent learns and acts on its own",
}
ALGORITHMS = {
    "ppo": "PPO: on-policy, clipped updates",
    "appo": "APPO: asynchronous PPO with V-trace",
    "sac": "SAC: off-policy, maximum entropy",
}
# Hyperparameters per algorithm (02 §3.8): name -> kind. Empty = RLlib default.
PARAMS: dict[str, dict[str, str]] = {
    "ppo": {
        "lr": "float",
        "gamma": "float",
        "lambda_": "float",
        "use_gae": "bool",
        "use_critic": "bool",
        "num_epochs": "int",
        "minibatch_size": "int",
        "train_batch_size_per_learner": "int",
        "clip_param": "float",
        "vf_loss_coeff": "float",
        "vf_clip_param": "float",
        "entropy_coeff": "float",
        "kl_coeff": "float",
        "grad_clip": "float",
    },
    "appo": {
        "lr": "float",
        "gamma": "float",
        "vtrace": "bool",
        "lambda_": "float",
        "clip_param": "float",
        "vtrace_clip_rho_threshold": "float",
        "vtrace_clip_pg_rho_threshold": "float",
        "entropy_coeff": "float",
        "kl_coeff": "float",
        "grad_clip": "float",
        "train_batch_size_per_learner": "int",
    },
    "sac": {
        "actor_lr": "float",
        "critic_lr": "float",
        "alpha_lr": "float",
        "initial_alpha": "float",
        "gamma": "float",
        "tau": "float",
        "twin_q": "bool",
        "target_entropy": "auto",
        "n_step": "int",
        "replay_buffer.capacity": "int",
        "num_steps_sampled_before_learning_starts": "int",
        "train_batch_size_per_learner": "int",
        "grad_clip": "float",
        "batch_mode": "batch_mode",
    },
}
METRICS = {
    "served_demand": "Served demand",
    "unmet_demand": "Unmet demand",
    "curtailment": "Curtailment",
    "p2p_share": "P2P share",
    "costs": "Costs",
    "violations": "Grid violations",
    "losses": "Losses",
    "rl_return": "RL return",
}
YES_NO = {"default": "RLlib default", "yes": "yes", "no": "no"}


@ui.page("/build/rl")
def rl_page() -> None:
    """RL (05 §6): paradigms × algorithms, hyperparameters, tuning, evaluation,
    baselines, sweep, resources and outputs of the draft.
    """
    s = services()
    draft = current_draft()
    resolved = s.config.resolve(draft)
    learning, evaluation = resolved.learning, resolved.evaluation
    form = DraftForm(draft)
    bind = form.bind
    with shell(
        "rl",
        "RL",
        "How the agents learn: paradigms × algorithms, hyperparameters, tuning, "
        "evaluation, baselines, sweep and resources",
    ):
        with stat_grid():
            runs_stat = ui.column().classes("w-full")
            cells_stat = ui.column().classes("w-full")
            budget_stat = ui.column().classes("w-full")

        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            with section(
                "Paradigms × algorithms",
                "Every ticked paradigm runs with every ticked algorithm and seed",
                "grid_on",
                classes="basis-1/3 min-w-0",
            ):
                paradigms = _ticks(
                    form, "learning.paradigms", PARADIGMS, learning.get("paradigms")
                )
                ui.separator()
                algorithms = _ticks(
                    form, "learning.algorithms", ALGORITHMS, learning.get("algorithms")
                )
                ui.separator()
                matrix = ui.column().classes("w-full gap-0")
                seeds = ui.input(
                    "Seeds", value=", ".join(str(x) for x in learning.get("seeds", []))
                ).classes("w-full")
                form.elements.append(seeds)
                form.track("learning.seeds", lambda: _ints(seeds.value))
                ui.label(
                    "One run per seed and cell; use at least three seeds to compare."
                ).classes("mls-card-caption")
                budget = learning.get("budget", {})
                with ui.row().classes("no-wrap gap-2 w-full"):
                    unit = bind(
                        "learning.budget.unit",
                        ui.select(
                            {
                                "env_steps": "Environment steps",
                                "iterations": "Iterations",
                                "episodes": "Episodes",
                            },
                            value=budget.get("unit", "iterations"),
                            label="Budget unit",
                        ).classes("grow"),
                    )
                    value = bind(
                        "learning.budget.value",
                        ui.number("Budget", value=budget.get("value"), min=1).classes(
                            "grow"
                        ),
                        int,
                    )
                ui.label(
                    "Environment steps keep the budget equal across paradigms and "
                    "algorithms (I-50)."
                ).classes("mls-card-caption")

            with section(
                "Algorithm parameters",
                "Pre-filled with the original MARLEM values (02 §3.8); empty = the "
                "RLlib default of the pinned version",
                "tune",
                classes="grow basis-0 min-w-0",
            ):
                params = learning.get("algorithm_params", {})
                with ui.tabs().classes("w-full") as tabs:
                    for a in ALGORITHMS:
                        ui.tab(a, label=a.upper())
                with ui.tab_panels(tabs, value="ppo").classes("w-full"):
                    for a, names in PARAMS.items():
                        with ui.tab_panel(a):
                            with ui.grid(columns=3).classes("w-full gap-2"):
                                for name, kind in names.items():
                                    _param(form, a, name, kind, params.get(a, {}))

        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            with section("Paradigm options", icon="hub", classes="grow basis-0"):
                options = learning.get("paradigm_options", {})
                for p in ("ctce", "ctde"):
                    bind(
                        f"learning.paradigm_options.{p}.reward_aggregation",
                        ui.select(
                            {"sum": "Sum (original)", "mean": "Mean (I-73)"},
                            value=options.get(p, {}).get("reward_aggregation", "sum"),
                            label=f"{p.upper()} group reward",
                        ).classes("w-full"),
                    )
                bind(
                    "learning.paradigm_options.ctde.critic_input",
                    ui.select(
                        {
                            "joint_obs_actions": "Joint observations and actions",
                            "joint_obs": "Joint observations",
                        },
                        value=options.get("ctde", {}).get(
                            "critic_input", "joint_obs_actions"
                        ),
                        label="CTDE critic input",
                    ).classes("w-full"),
                )
                bind(
                    "learning.paradigm_options.dtde.policy_sharing",
                    ui.select(
                        {
                            "independent": "One policy per agent (original)",
                            "shared": "One shared policy",
                        },
                        value=options.get("dtde", {}).get(
                            "policy_sharing", "independent"
                        ),
                        label="DTDE policies",
                    ).classes("w-full"),
                )
                model = learning.get("model", {})
                with ui.row().classes("no-wrap gap-2 w-full"):
                    bind(
                        "learning.model.embeddings_dim",
                        ui.number(
                            "Encoder width (CTCE/CTDE)",
                            value=model.get("embeddings_dim"),
                            min=1,
                        ).classes("grow"),
                        int,
                    )
                    bind(
                        "learning.model.activation",
                        ui.select(
                            ["relu", "tanh", "swish", "linear"],
                            value=model.get("activation", "relu"),
                            label="Activation",
                        ).classes("grow"),
                    )
                hiddens = ui.input(
                    "DTDE hidden layers",
                    value=", ".join(str(x) for x in model.get("dtde_hiddens") or []),
                    placeholder="e.g. 256, 256; empty = RLlib default",
                ).classes("w-full")
                form.elements.append(hiddens)
                form.track(
                    "learning.model.dtde_hiddens", lambda: _ints(hiddens.value) or None
                )

            with section(
                "Tuning and checkpoints",
                "Population Based Training (I-62: always on in the original)",
                "auto_graph",
                classes="grow basis-0",
            ):
                tuning = learning.get("tuning", {})
                method = bind(
                    "learning.tuning.method",
                    ui.toggle(
                        {"none": "No tuning", "pbt": "PBT"},
                        value=tuning.get("method", "pbt"),
                    ).props("no-caps dense"),
                )
                with ui.column().classes("w-full gap-1") as pbt_box:
                    with ui.row().classes("no-wrap gap-2 w-full"):
                        bind(
                            "learning.tuning.num_samples",
                            ui.number(
                                "Population", value=tuning.get("num_samples"), min=1
                            ).classes("grow"),
                            int,
                        )
                        bind(
                            "learning.tuning.perturbation_interval",
                            ui.number(
                                "Perturb every (iterations)",
                                value=tuning.get("perturbation_interval"),
                                min=1,
                            ).classes("grow"),
                            int,
                        )
                    bind(
                        "learning.tuning.metric",
                        ui.input(
                            "Selection metric",
                            value=tuning.get(
                                "metric", "env_runners/episode_return_mean"
                            ),
                        ).classes("w-full"),
                    )
                    _json_field(
                        form,
                        "learning.tuning.mutations",
                        "Mutation domains (JSON)",
                        tuning.get("mutations"),
                        '{"ppo": {"lr": {"dist": "loguniform", "low": 1e-4, '
                        '"high": 1e-2}}}',
                        dict,
                    )
                    ui.label(
                        "Per algorithm: parameter → distribution. Each domain must "
                        "contain the parameter's start value (I-49)."
                    ).classes("mls-card-caption")
                checkpoint = learning.get("checkpoint", {})
                with ui.row().classes("no-wrap gap-2 w-full"):
                    bind(
                        "learning.checkpoint.every",
                        ui.number(
                            "Checkpoint every", value=checkpoint.get("every"), min=1
                        ).classes("grow"),
                        int,
                    )
                    bind(
                        "learning.checkpoint.keep",
                        ui.number("Keep", value=checkpoint.get("keep"), min=1).classes(
                            "grow"
                        ),
                        int,
                    )
                rollout = learning.get("rollout", {})
                with ui.row().classes("no-wrap gap-2 w-full"):
                    for key, label in (
                        ("num_env_runners", "Env runners"),
                        ("envs_per_runner", "Envs per runner"),
                        ("rollout_fragment_length", "Fragment length"),
                    ):
                        bind(
                            f"learning.rollout.{key}",
                            ui.number(label, value=rollout.get(key), min=1).classes(
                                "grow"
                            ),
                            int,
                        )
                ui.label("Empty: as many env runners as CPUs; RLlib defaults.").classes(
                    "mls-card-caption"
                )

            with section(
                "Evaluation and baselines",
                "How policies are judged, and against what",
                "fact_check",
                classes="grow basis-0",
            ):
                with ui.row().classes("no-wrap gap-2 w-full"):
                    bind(
                        "evaluation.interval",
                        ui.number(
                            "Every (iterations)",
                            value=evaluation.get("interval"),
                            min=1,
                        ).classes("grow"),
                        int,
                    )
                    episodes = ui.input(
                        "Episodes", value=str(evaluation.get("episodes", "auto"))
                    ).classes("grow")
                    form.elements.append(episodes)
                    form.track("evaluation.episodes", lambda: _auto_int(episodes.value))
                bind(
                    "evaluation.days",
                    ui.select(
                        {
                            "holdout": "Held-out days (never trained on)",
                            "train": "Training days (the original, I-72)",
                        },
                        value=evaluation.get("days", "holdout"),
                        label="Evaluation days",
                    ).classes("w-full"),
                )
                eval_seeds = ui.input(
                    "Evaluation seeds",
                    value=", ".join(str(x) for x in evaluation.get("seeds") or []),
                    placeholder="disjoint from the training seeds",
                ).classes("w-full")
                form.elements.append(eval_seeds)
                form.track("evaluation.seeds", lambda: _ints(eval_seeds.value) or None)
                bind(
                    "evaluation.explore",
                    ui.switch(
                        "Explore while evaluating",
                        value=evaluation.get("explore", False),
                    ),
                )
                bind(
                    "evaluation.parallel_to_training",
                    ui.switch(
                        "Evaluate in parallel to training",
                        value=evaluation.get("parallel_to_training", True),
                    ),
                )
                bind(
                    "evaluation.metrics",
                    ui.select(
                        METRICS,
                        value=list(evaluation.get("metrics") or METRICS),
                        label="Metrics",
                        multiple=True,
                    )
                    .classes("w-full")
                    .props("use-chips"),
                )
                ui.separator()
                ui.label("Baselines").classes("text-weight-medium")
                _baselines(form, resolved.baselines)

        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            with section(
                "Sweep",
                "Variants of one setting in one file (02 §3.11)",
                "call_split",
                classes="grow basis-0",
            ):
                sweep = resolved.sweep or {}
                sweep_mode = ui.toggle(
                    {"grid": "Every combination", "zip": "Paired lists"},
                    value=sweep.get("mode", "grid"),
                ).props("no-caps dense")
                sweep_params = _json_field(
                    None,
                    "",
                    "Parameters (JSON: path → values)",
                    sweep.get("parameters"),
                    '{"market.mechanism": ["average", "buyer", "seller"]}',
                    dict,
                )
                labels = ui.input(
                    "Labels",
                    value=", ".join(sweep.get("labels") or []),
                    placeholder="optional, one per point",
                ).classes("w-full")
                form.elements += [sweep_mode, sweep_params, labels]
                form.track(
                    "sweep",
                    lambda: _sweep(sweep_mode.value, sweep_params.value, labels.value),
                )
                ui.label(
                    "A path is a dotted field of the file, e.g. market.mechanism or "
                    "dso.fees.charged. 'Every combination' multiplies the lists; "
                    "'paired lists' takes them side by side (equal lengths)."
                ).classes("mls-card-caption")

            with section(
                "Resources and outputs",
                "Machine settings and what is saved",
                "dns",
                classes="grow basis-0",
            ):
                res, out = resolved.resources, resolved.outputs
                with ui.row().classes("no-wrap gap-2 w-full"):
                    for key, label in (
                        ("cpus_per_run", "CPUs per run"),
                        ("gpus_per_learner", "GPUs per learner"),
                        ("max_parallel_runs", "Runs at once"),
                    ):
                        bind(
                            f"resources.{key}",
                            ui.number(label, value=res.get(key), min=0).classes("grow"),
                            int,
                        )
                ui.label(
                    "Empty CPUs/GPUs: all detected. GPUs were slower than CPUs on "
                    "this machine; 0 is recommended."
                ).classes("mls-card-caption")
                bind(
                    "outputs.record_steps",
                    ui.select(
                        {
                            "none": "Nothing per step",
                            "evaluation": "Every step of evaluation episodes",
                            "all": "Every step (large)",
                        },
                        value=out.get("record_steps", "evaluation"),
                        label="Step records",
                    ).classes("w-full"),
                )
                bind(
                    "outputs.grid_element_results",
                    ui.switch(
                        "Per-bus and per-line results (large)",
                        value=out.get("grid_element_results", False),
                    ),
                )
                figures = ui.input(
                    "Figures to render at the end",
                    value=", ".join(out.get("figures") or []),
                ).classes("w-full")
                form.elements.append(figures)
                form.track("outputs.figures", lambda: _words(figures.value))

        with ui.row().classes("justify-end w-full gap-2"):
            ui.button("Apply to draft", icon="save", on_click=form.apply).props(
                "unelevated"
            )
            ui.button(
                "Continue to the summary",
                icon="arrow_forward",
                on_click=lambda: ui.navigate.to("/build/summary"),
            ).props("outline")

    def refresh() -> None:
        """Count the runs of the unsaved plan; show the fields that apply."""
        pbt_box.set_visibility(method.value == "pbt")
        matrix.clear()
        with matrix:
            _matrix(paradigms(), algorithms())
        for box in (runs_stat, cells_stat, budget_stat):
            box.clear()
        try:
            changes = form.changes()
            plan = s.config.update(draft, changes)
            runs = s.config.expand(plan)
            error = ""
        except (ValueError, TypeError) as e:
            runs, error = [], str(e)
        train = [r for r in runs if r.kind == "train"]
        with runs_stat:
            stat(
                "Runs",
                str(len(runs)) if not error else "—",
                error or f"{len(train)} training, {len(runs) - len(train)} baseline",
                "play_circle",
                tone="negative" if error else "primary",
            )
        with cells_stat:
            stat(
                "Cells",
                f"{len(paradigms())} × {len(algorithms())}",
                "paradigms × algorithms",
                "grid_on",
            )
        with budget_stat:
            stat(
                "Budget per run",
                f"{int(value.value or 0):,}",
                unit.value.replace("_", " "),
                "speed",
            )

    for control in form.elements:
        control.on_value_change(refresh)
    refresh()


def _ticks(
    form: DraftForm, path: str, options: dict[str, str], chosen: list | None
) -> Callable[[], list[str]]:
    """Checkboxes for a list field; returns a function giving the ticked keys."""
    boxes = {}
    for key, label in options.items():
        boxes[key] = ui.checkbox(label, value=key in (chosen or []))
    form.elements += list(boxes.values())

    def ticked() -> list[str]:
        return [k for k, box in boxes.items() if box.value]

    form.track(path, ticked)
    return ticked


def _matrix(paradigms: list[str], algorithms: list[str]) -> None:
    """The cells that will run, as a small read-only grid."""
    with ui.grid(columns=4).classes("items-center gap-1"):
        ui.label("")
        for a in ALGORITHMS:
            ui.label(a.upper()).classes("text-weight-bold text-center text-caption")
        for p in PARADIGMS:
            ui.label(p.upper()).classes("text-weight-bold text-caption")
            for a in ALGORITHMS:
                on = p in paradigms and a in algorithms
                ui.icon("check_circle" if on else "radio_button_unchecked").classes(
                    "text-primary" if on else "text-grey-5"
                )


def _param(form: DraftForm, algo: str, name: str, kind: str, values: dict) -> None:
    """One hyperparameter control, bound to ``learning.algorithm_params``."""
    path = f"learning.algorithm_params.{algo}.{name}"
    value: Any = values
    for key in name.split("."):
        value = value.get(key) if isinstance(value, dict) else None
    if kind == "bool":
        current = "default" if value is None else ("yes" if value else "no")
        form.bind(
            path,
            ui.select(YES_NO, value=current, label=name),
            lambda v: {"yes": True, "no": False}.get(v),
        )
    elif kind == "auto":
        field = ui.input(name, value="" if value is None else str(value))
        form.elements.append(field)
        form.track(path, lambda: _auto_float(field.value))
    elif kind == "batch_mode":
        form.bind(
            path,
            ui.select(
                {
                    "complete_episodes": "complete episodes",
                    "truncate_episodes": "truncate episodes",
                },
                value=value or "complete_episodes",
                label=name,
            ),
        )
    else:
        form.bind(
            path,
            ui.number(name, value=value, format="%.6g" if kind == "float" else None),
            float if kind == "float" else int,
        )


def _baselines(form: DraftForm, baselines: list) -> None:
    """Checkboxes for the baselines; rule-based with its strategy."""
    names = {b if isinstance(b, str) else b.get("name") for b in baselines}
    rule = next(
        (b for b in baselines if isinstance(b, dict) and b.get("name") == "rule_based"),
        {},
    )
    no_order = ui.checkbox("no_order: agents never trade", value="no_order" in names)
    random = ui.checkbox(
        "random: zero-intelligence orders ([P1] §4.2)", value="random" in names
    )
    rule_based = ui.checkbox("rule_based", value="rule_based" in names)
    strategy = ui.select(
        {"net_position": "Net position: sell surplus, buy deficit at the midpoint"},
        value=rule.get("strategy", "net_position"),
        label="Rule",
    ).classes("w-full")
    form.elements += [no_order, random, rule_based, strategy]

    def entries() -> list:
        out: list = [
            n for n, box in (("no_order", no_order), ("random", random)) if box.value
        ]
        if rule_based.value:
            out.append({"name": "rule_based", "strategy": strategy.value})
        return out

    form.track("baselines", entries)
    ui.label(
        "A policy is only good if it beats doing nothing and trading at random."
    ).classes("mls-card-caption")


def _json_field(
    form: DraftForm | None,
    path: str,
    label: str,
    value: Any,
    example: str,
    kind: type,
) -> ui.textarea:
    """A JSON text field; red while it does not parse. Bound to ``path`` if given."""
    field = (
        ui.textarea(label, value=json.dumps(value, indent=1) if value else "")
        .classes("w-full")
        .props(
            f"placeholder='{example}' autogrow input-style=\"font-family: monospace\""
        )
    )

    def check() -> None:
        try:
            _parse_json(field.value, kind)
            field.props(remove="error")
        except ValueError as e:
            field.props(f'error error-message="{e}"')

    field.on_value_change(check)
    if form is not None:
        form.elements.append(field)
        form.track(path, lambda: _safe_json(field.value, kind, value))
    return field


def _parse_json(text: str, kind: type) -> Any:
    """Parsed JSON of ``kind``, ``None`` for empty text; ``ValueError`` otherwise."""
    if not (text or "").strip():
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Not JSON: {e.msg}") from None
    if not isinstance(data, kind):
        raise ValueError(f"Expected a JSON {kind.__name__}")
    return data


def _safe_json(text: str, kind: type, fallback: Any) -> Any:
    """Parsed JSON, or the original value while the text does not parse."""
    try:
        return _parse_json(text, kind)
    except ValueError:
        return fallback


def _sweep(mode: str, parameters: str, labels: str) -> dict:
    """The ``sweep`` section from the controls (empty: no sweep)."""
    try:
        params = _parse_json(parameters, dict)
    except ValueError:
        params = None
    if not params:
        return {}
    out: dict[str, Any] = {"mode": mode, "parameters": params}
    names = _words(labels)
    if names:
        out["labels"] = names
    return out


def _ints(text: str | None) -> list[int]:
    """Integers from ``"1, 2, 3"``; non-numbers are skipped."""
    return [int(x) for x in _words(text) if x.lstrip("-").isdigit()]


def _words(text: str | None) -> list[str]:
    """Items of a comma-separated list."""
    return [x.strip() for x in (text or "").split(",") if x.strip()]


def _auto_int(text: str | None) -> int | str:
    """``"auto"`` or an integer."""
    text = (text or "auto").strip()
    return int(text) if text.isdigit() else "auto"


def _auto_float(text: str | None) -> float | str | None:
    """``"auto"``, a number, or ``None`` when empty."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return "auto"
