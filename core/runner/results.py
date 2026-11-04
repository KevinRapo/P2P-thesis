"""Results of runs, read from their folders: what the Studio's Results page and the
notebooks compare.

A run is identified by its target, experiment and run name (``RunRef``). This PC's
runs are in the runs root; a cluster's, once synced (``Target.sync``), in its mirror
(``runs/@<target>/``). The mirror is the cluster's run, copied: it is listed under
the cluster's name, never as a second run. Only the saved files are read
(``experiment.json``, ``run.json``, the CSVs of ``core/rl/train.py`` and
``core/runner/launch.py``): nothing here starts Ray, builds a market or connects to
a cluster, and a table is read only when it is asked for.

Two different units: an evaluation episode (one day) and a training seed (one run).
The spread over seeds comes from separate runs (``indicators.py``), never from the
days or the participants of one run.

    find_runs()                  every run of this PC and of the synced mirrors
    load_runs(refs)              their ``RunResult``: settings, state, tables
    overview(results)            one row per run: settings, state, held-out money
    learning_curves(results)     evaluation return and money over environment steps
    training_curves(results)     training return over environment steps
    learner_metrics(results)     the learner over environment steps, long format:
                                 per module (losses, entropy, KL, gradient norm)
                                 and per action part (``LEARNER_GROUPS``,
                                 ``PART_STATS``); any environment
    participant_metrics(results) every number of a participant on a test day, long
                                 format
    participant_days(result)     one run, per test day and participant: the same
    participant_groups(result)   what kind each participant is: battery, PV or other
    participant_gains(results)   per run and participant: its gain over ``zero``
    trade_table(results)         every held-out trade of every run, with its place
                                 in the price band
    day_indicators(results)      every indicator per run, policy and test day, long
                                 format, with what the run was (``indicators.py``)
    differing_settings(results)  the settings that are not the same in all runs
                                 (their full saved values)
"""

from __future__ import annotations

import functools
import hashlib
import json
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

import numpy as np
import pandas as pd
from pandas.api.types import union_categoricals

from core.config.scenario import flat_prices
from core.runner import indicators, registry
from core.runner.registry import RunState
from core.runner.spec import MARKET_ENVS, REPO, runs_root

LOCAL = "local"
BASELINES = ("zero", "net_position")
TRAINED = "trained"
UNKNOWN_GROUP = "unknown"  # a participant the run's scenario does not list
# A run folder's name: <algorithm>_<paradigm>_s<seed>[_<variant>] (``spec.expand``).
_RUN_NAME = re.compile(r"^(?P<algorithm>[a-z]+)_(?P<paradigm>[a-z]+)_s(?P<seed>\d+)")


# --------------------------------------------------------------------------------------
# Finding runs
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class RunRef:
    """Where one run is: its target, experiment, name and folder on this PC."""

    target: str
    experiment: str
    run: str
    folder: Path

    @property
    def key(self) -> str:
        """``target/experiment/run``: the run's one name."""
        return f"{self.target}/{self.experiment}/{self.run}"


def sources() -> dict[str, Path]:
    """Where runs are read from: this PC's runs root, and the mirror of each cluster
    target in ``hpc/targets.toml`` (one whose settings are complete)."""
    from core.runner import targets

    found = {LOCAL: runs_root()}

    for name, settings in targets.settings().items():
        mirror = settings.get("mirror")
        if settings.get("kind") == "slurm" and isinstance(mirror, str):
            found[name] = REPO / mirror

    return found


def find_runs(
    where: Optional[dict[str, Path]] = None,
    experiments: Optional[Sequence[tuple[str, str]]] = None,
) -> list[RunRef]:
    """Every run folder of every source (default ``sources()``), by target,
    experiment and run name; with ``experiments`` (``(target, experiment)`` pairs)
    only theirs. An experiment in a folder is named ``<folder>/<experiment>``
    (``registry.grouped_experiments``). A mirror inside the runs root is not read
    twice."""
    where = where or sources()
    mirrors = {Path(p).resolve() for t, p in where.items() if t != LOCAL}
    found = []

    for target, root in where.items():
        root = Path(root)

        if experiments is None:
            names = registry.grouped_experiments(root)
        else:
            names = [e for t, e in experiments if t == target and (root / e).is_dir()]

        for experiment in names:
            folder = root / experiment
            inside = {folder.resolve(), *folder.resolve().parents}
            if inside & mirrors and target == LOCAL:
                continue
            for run_dir in sorted(folder.iterdir()):
                if registry._is_run_dir(run_dir):
                    found.append(RunRef(target, experiment, run_dir.name, run_dir))

    return found


# --------------------------------------------------------------------------------------
# One run
# --------------------------------------------------------------------------------------
@dataclass
class RunResult:
    """One run: its settings, its state, and its tables (read when asked for).

    Attributes:
        ref: Where it is.
        settings: What it was, as saved: ``kind`` (``run_kind``), ``algorithm``,
            ``paradigm``, ``seed``, ``variant``, ``test`` (a test-profile run), ``scenario`` (its contents,
            or its file name in older runs), ``train_days`` and ``test_days`` (every
            day), ``budget``, ``overrides`` (the training settings it ran with),
            ``grad_clip`` (the effective gradient clip), ``kl_logged`` (whether the
            learner computed the KL), ``model``, ``commit``, ``uncommitted``; None
            where the files do not say. Compare these; show ``labels``.
        state: Its ``RunState`` (None if the folder cannot be read as a run).
    """

    ref: RunRef
    settings: dict[str, Any]
    state: Optional[RunState]

    @property
    def key(self) -> str:
        return self.ref.key

    @property
    def labels(self) -> dict[str, Any]:
        """The settings shortened for display: the scenario's name, days as
        ``first … last (n)``; the training settings and model left out (they are
        shown on their own)."""
        settings = self.settings
        scenario = settings["scenario"]

        if isinstance(scenario, dict):
            scenario = scenario.get("name", "(unnamed)")

        apart = ("env_config", "overrides", "model")
        shown = {k: v for k, v in settings.items() if k not in apart}

        return shown | {
            "scenario": scenario,
            "train_days": _days(settings["train_days"]),
            "test_days": _days(settings["test_days"]),
        }

    def has(self, name: str) -> bool:
        """Whether the run has the table ``<name>``, without reading it."""
        return _table_path(self.ref.folder, name).is_file()

    def table(self, name: str) -> Optional[pd.DataFrame]:
        """The run's ``<name>.csv`` or ``<name>.csv.gz`` (e.g.
        ``"heldout_episodes"``), None if it has none; read again only when the file
        has changed (a running run's grow). Shared between callers: copy before
        changing it."""
        return _table(_table_path(self.ref.folder, name))


def _table_path(folder: Path, name: str) -> Path:
    """Where a run's table is: ``<name>.csv``, or compressed."""
    packed = folder / f"{name}.csv.gz"

    return packed if packed.is_file() else folder / f"{name}.csv"


def _table(path: Path) -> Optional[pd.DataFrame]:
    try:
        found = path.stat()
    except OSError:
        return None

    return _read_csv(str(path), found.st_mtime_ns, found.st_size)


def _latest(paths: int, megabytes: float = float("inf")) -> Callable[[Callable], Callable]:
    """``build(path, *stamp)`` remembered per path, only for the latest ``stamp`` (a
    file that keeps growing in a live view holds one entry, not one per version), and
    for the paths used most recently: at most ``paths`` of them and, of tables, about
    ``megabytes`` (the newest is always kept). A long session that opens many
    experiments keeps the latest ones, and reads an older one again when it comes
    back. Safe from the Studio's worker threads; ``cached.clear()`` forgets all."""
    budget = megabytes * 1e6

    def decorate(build: Callable) -> Callable:
        kept: "OrderedDict[str, tuple]" = OrderedDict()  # path -> (stamp, value, bytes)
        lock = threading.Lock()

        @functools.wraps(build)
        def cached(path: str, *stamp: Any) -> Any:
            with lock:
                found = kept.get(path)

                if found is not None and found[0] == stamp:
                    kept.move_to_end(path)
                    return found[1]

            value = build(path, *stamp)  # outside the lock: reads run side by side
            size = _bytes(value)

            with lock:
                kept[path] = (stamp, value, size)
                kept.move_to_end(path)
                held = sum(entry[2] for entry in kept.values())

                while len(kept) > 1 and (len(kept) > paths or held > budget):
                    held -= kept.popitem(last=False)[1][2]

            return value

        cached.clear = kept.clear  # type: ignore[attr-defined]
        cached.kept = kept  # type: ignore[attr-defined]  (for tests)
        return cached

    return decorate


def _bytes(value: Any) -> int:
    """A cached value's memory: a table's, strings included; anything else 0."""
    if isinstance(value, pd.DataFrame):
        return int(value.memory_usage(deep=True).sum())

    return 0


# What each cache keeps: a run has about ten tables, of a few kB to tens of MB (the
# step tables of a large network), so a memory budget besides a number of paths.
CSV_PATHS, CSV_MB = 512, 256
LEARNER_PATHS, LEARNER_MB = 128, 64
DAY_PATHS, DAY_MB = 256, 32


@_latest(CSV_PATHS, CSV_MB)
def _read_csv(path: str, mtime_ns: int, size: int) -> Optional[pd.DataFrame]:
    """A table, cached by its file's path, time and size: an unchanged file is
    read once."""
    try:
        return pd.read_csv(path)
    except (OSError, EOFError, ValueError, pd.errors.EmptyDataError):
        return None


def load_run(ref: RunRef) -> RunResult:
    """A run's settings and state, from its folder and its experiment's: its arm's
    ``experiment.json``; older runs have ``experiment_<variant>.json`` next to their
    folder, or only the experiment's."""
    record = registry.read_json(ref.folder / "run.json") or {}
    name = _RUN_NAME.match(ref.run)
    seed = record.get("seed", int(name["seed"]) if name else None)
    variant = None
    spec = registry.read_json(ref.folder / "experiment.json")

    if name and len(ref.run) > name.end():
        variant = ref.run[name.end() + 1 :]
        older = ref.folder.parent / f"experiment_{variant}.json"
        spec = spec or registry.read_json(older)

    spec = spec or registry.read_json(ref.folder.parent / "experiment.json") or {}
    git = record.get("git") or {}
    settings = {
        "kind": run_kind(record.get("env_class") or spec.get("env")),
        "algorithm": record.get("algorithm", name["algorithm"] if name else None),
        "paradigm": record.get("paradigm", name["paradigm"] if name else None),
        "seed": seed,
        "variant": variant,
        "test": ref.experiment.endswith("--test"),
        "scenario": spec.get("scenario"),
        "train_days": spec.get("train_days"),
        "test_days": spec.get("test_days"),
        "env_config": spec.get("env_config"),
        "budget": record.get("budget_env_steps"),
        "overrides": record.get("settings"),
        # The gradient clip the run trained with (given or RLlib's default), and
        # whether its learner computed the KL (with it off RLlib logs a constant 0).
        "grad_clip": (record.get("settings_effective") or {}).get("grad_clip"),
        "kl_logged": (record.get("settings_effective") or {}).get("use_kl_loss"),
        "model": record.get("model"),
        "commit": (git.get("commit") or "")[:8] or None,
        "uncommitted": git.get("uncommitted_changes"),
    }

    return RunResult(ref, settings, registry.run_state(ref.folder))


def run_kind(env: Optional[str]) -> Optional[str]:
    """What a run trained on, from its environment (``run.json``'s ``env_class``,
    else its experiment's ``env``): ``"market"``, ``"probe"`` (an RL probe of
    ``core/rl/envs/probes.py``), ``"other"``, or None when nothing says yet."""
    if not env:
        return None

    if env in MARKET_ENVS:
        return "market"

    return "probe" if env.startswith("core.rl.envs.probes:") else "other"


def load_runs(refs: Sequence[RunRef]) -> list[RunResult]:
    return [load_run(ref) for ref in refs]


def _days(value: Any) -> Optional[str]:
    """Days as one label: ``first … last (n)``."""
    if not value:
        return None

    if isinstance(value, dict):
        return f"{value.get('from')} … {value.get('to')}"

    return f"{value[0]} … {value[-1]} ({len(value)})" if len(value) > 1 else value[0]


# --------------------------------------------------------------------------------------
# Many runs: tables to compare
# --------------------------------------------------------------------------------------
def _head(result: RunResult) -> dict[str, Any]:
    ref = result.ref
    return {
        "key": ref.key,
        "target": ref.target,
        "experiment": ref.experiment,
        "run": ref.run,
        **{k: result.settings[k] for k in ("algorithm", "paradigm", "seed", "variant")},
    }


def _agents(frame: pd.DataFrame) -> int:
    """Number of agents in a summary with ``return/<agent>`` columns (at least 1)."""
    return max(1, sum(c.startswith("return/") for c in frame.columns))


def _started(state: Optional[RunState]) -> Optional[str]:
    """When a run started, as ``2026-11-02 18:13`` (None when nothing says): text that
    sorts by time."""
    if not state or not state.started:
        return None

    return str(state.started)[:16].replace("T", " ")


def overview(results: Sequence[RunResult]) -> pd.DataFrame:
    """One row per run: what it was, when it started, how far it got, and its
    held-out team money per day for the trained policy and each baseline
    (``heldout_agents.csv``)."""
    rows = []

    for result in results:
        state = result.state
        row = _head(result) | {
            "kind": result.settings["kind"],
            "test": result.settings["test"],
            "state": state.state if state else None,
            "started": _started(state),
            "env_steps": state.env_steps if state else None,
            "budget": result.settings["budget"],
            "commit": result.settings["commit"],
        }
        people = result.table("heldout_agents")

        if people is not None and "bill" in people:
            money = people.groupby(["policy", "day"]).bill.sum().groupby("policy")
            row["participants"] = people.agent.nunique()

            for policy, value in money.mean().items():
                row[f"money_{policy}"] = value

        rows.append(row)

    return pd.DataFrame(rows)


def learning_curves(results: Sequence[RunResult]) -> pd.DataFrame:
    """Evaluation during training (``evaluation.csv``): one row per run, evaluation
    point and policy, with the team return, its mean per participant and the team's
    money (``evaluation_agents.csv``; empty for an environment without a bill)."""
    frames = []

    for result in results:
        frame = result.table("evaluation")

        if frame is None:
            continue

        frame = frame[["env_steps", "policy", "team_return_mean"]].copy()
        frame["per_participant"] = frame.team_return_mean / _agents(
            result.table("evaluation")
        )
        people = result.table("evaluation_agents")

        if people is not None and "bill" in people:
            days = people.groupby(["env_steps", "policy", "episode"]).bill.sum()
            money = days.groupby(["env_steps", "policy"]).mean().rename("team_money")
            frame = frame.join(money, on=["env_steps", "policy"])

        frames.append(frame.assign(**_head(result)))

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def training_curves(results: Sequence[RunResult]) -> pd.DataFrame:
    """Training return over environment steps (``metrics.csv``), one row per run
    and progress report: what the sampled episodes earned while learning, a
    different measurement from the evaluation."""
    frames = []

    for result in results:
        frame = result.table("metrics")

        if frame is None or "team_return_mean" not in frame:
            continue

        frame = frame[["env_steps", "team_return_mean"]].copy()
        counted = result.table("evaluation")  # how many participants
        agents = _agents(counted) if counted is not None else 1
        frame["per_participant"] = frame.team_return_mean / agents
        frames.append(frame.assign(**_head(result)))

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# What the learner reports per module and action part (``core/rl/train.py``), in
# groups that read together: (title, metrics, what to look for). Nothing in them is
# specific to an environment.
LEARNER_GROUPS: list[tuple[str, list[str], str]] = [
    (
        "Policy loss",
        ["policy_loss"],
        "PPO's clipped surrogate (negated); its trend matters less than its noise",
    ),
    (
        "Value loss",
        ["vf_loss", "vf_loss_unclipped"],
        "the critic's squared error against its targets; should fall, then settle",
    ),
    (
        "Value fit",
        ["vf_explained_var"],
        "explained variance of the targets by the critic: 1 is a perfect fit, "
        "0 no better than their mean",
    ),
    (
        "Entropy",
        ["entropy"],
        "the action distribution's entropy, summed over the parts: falls as the "
        "policy sharpens; a Gaussian's can go below 0",
    ),
    (
        "Update size (KL)",
        ["mean_kl_loss"],
        "KL between the collecting and the updated policy: about 0.01-0.02 is a "
        "usual step; near 0 means nothing moves",
    ),
    (
        "Clip fraction",
        ["clip_fraction"],
        "share of samples whose ratio is outside [1 - clip, 1 + clip], where the "
        "clipped objective can stop the policy gradient; about 0.1-0.2 is usual",
    ),
    (
        "Gradient norm",
        ["gradients_default_optimizer_global_norm"],
        "before clipping; above grad_clip (the dashed line) the whole update, actor "
        "and critic, is scaled down",
    ),
]
# Per action part (``core/rl/policy.part_stats``): a continuous part's mean, log σ
# and share of means outside [-1, 1]; a categorical part's entropy and the most
# likely category's probability.
PART_STATS = ("mean", "log_std", "outside", "entropy", "top")


def learner_metrics(results: Sequence[RunResult]) -> pd.DataFrame:
    """The learner of each run over environment steps (``metrics.csv``), long format:
    one row per run, progress report, module, part and metric, with ``value``.

    ``part`` is empty for a module's own metrics (``LEARNER_GROUPS``) and names the
    action part for its per-part statistics (``PART_STATS``); ``module`` is empty
    for the run's training return (``team_return_mean``). The modules' mean, min and
    max columns (``modules/...``) are left out: they follow from the rows. The KL
    (``mean_kl_loss``) is left out of a run whose learner did not compute it
    (``use_kl_loss`` off): RLlib then logs a constant 0, not a measurement.

    The text columns (``module``, ``part``, ``metric`` and the run's own, ``key``,
    ``run``, ...) are categoricals: a run has about 30,000 rows of a few dozen names,
    which as strings take 15 times the memory. Group by them with ``observed=True``."""
    frames = []

    for result in results:
        path = result.ref.folder / "metrics.csv"

        if path.is_file():
            found = path.stat()
            kl_logged = bool(result.settings.get("kl_logged"))
            rows = _learner_rows(str(path), found.st_mtime_ns, found.st_size, kl_logged)

            if rows is not None:
                one = np.zeros(len(rows), dtype=np.int8)  # every row the run's name
                head = {
                    name: pd.Categorical.from_codes(one, [value])
                    if isinstance(value, str)
                    else value
                    for name, value in _head(result).items()
                }
                frames.append(rows.assign(**head))

    return _concat_categories(frames)


def _concat_categories(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """``frames`` (the same columns) one under the other, their categorical columns
    still categorical: ``pd.concat`` turns a column into strings when the frames'
    categories differ, so those are joined with ``union_categoricals``."""
    if not frames:
        return pd.DataFrame()

    columns = {}

    for name in frames[0].columns:
        parts = [frame[name] for frame in frames]

        if all(isinstance(p.dtype, pd.CategoricalDtype) for p in parts):
            columns[name] = union_categoricals(parts)
        else:
            columns[name] = pd.concat(parts, ignore_index=True)

    return pd.DataFrame(columns)


@_latest(LEARNER_PATHS, LEARNER_MB)
def _learner_rows(
    path: str, mtime_ns: int, size: int, kl_logged: bool
) -> Optional[pd.DataFrame]:
    """One ``metrics.csv`` long, built once: at every live refresh only the runs still
    training cost anything."""
    frame = _read_csv(path, mtime_ns, size)

    if frame is None or "env_steps" not in frame:
        return None

    rows = []

    for column in frame.columns:
        pieces = column.split("/")

        if pieces[-1] == "mean_kl_loss" and not kl_logged:
            continue

        if column == "team_return_mean":
            module, part, metric = "", "", "team_return_mean"
        elif len(pieces) == 2 and pieces[0] != "modules":
            module, part, metric = pieces[0], "", pieces[1]
        elif len(pieces) == 3 and pieces[2] in PART_STATS:
            module, part, metric = pieces
        else:
            continue

        values = frame[["env_steps", column]].dropna()
        rows.append(
            pd.DataFrame(
                {
                    "env_steps": values.env_steps.to_numpy(),
                    "module": module,
                    "part": part,
                    "metric": metric,
                    "value": values[column].astype(float).to_numpy(),
                }
            )
        )

    if not rows:
        return None

    names = ["module", "part", "metric"]  # a few dozen names over ~30,000 rows

    return pd.concat(rows, ignore_index=True).astype({n: "category" for n in names})


# What a run saved of its time (``core/rl/train.py``): per progress report in
# ``metrics.csv`` and, once, in ``run.json``'s ``timings``.
TIMER_COLUMNS = (
    "train_call_s",
    "sampler_sample_s_mean",
    "sampling_s_mean",
    "learner_call_s_mean",
    "sampled_steps_per_train_s",
)
STAGE_COLUMNS = ("ray_init_s", "build_s", "train_calls_s", "evaluation_s", "checkpoint_s")


def iteration_timing(results: Sequence[RunResult]) -> pd.DataFrame:
    """Where each progress report's training call went (``metrics.csv``): one row per
    run and report, with ``env_steps``, the ``TIMER_COLUMNS`` (NaN where a run did not
    save one) and the call split into parts that add up to ``train_call_s``:

    - ``runners_s``: inside the env runners' own ``sample()`` (the market and the
      policy), ``sampler_sample_s_mean``; a run that did not save it counts the whole
      ``sampling_s_mean`` here;
    - ``sampling_overhead_s``: the rest of the driver's sampling timer
      (``sampling_s_mean``): waiting for the slowest runner and getting the episodes;
    - ``learner_call_s_mean``: the update;
    - ``unaccounted_s``: what is left of the call.

    RLlib's timers are smoothed means, so the parts are not exact for one iteration
    and a negative remainder counts as 0."""
    frames = []

    for result in results:
        frame = result.table("metrics")

        if frame is None or "env_steps" not in frame:
            continue

        found = pd.DataFrame({"env_steps": frame.env_steps})

        for column in TIMER_COLUMNS:
            found[column] = frame[column] if column in frame else float("nan")

        found["runners_s"] = found.sampler_sample_s_mean.fillna(found.sampling_s_mean)
        found["sampling_overhead_s"] = (found.sampling_s_mean - found.runners_s).clip(
            lower=0
        )
        driver = found.sampling_s_mean + found.learner_call_s_mean.fillna(0)
        found["unaccounted_s"] = (found.train_call_s - driver).clip(lower=0)
        frames.append(found.assign(**_head(result)))

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def run_timings(results: Sequence[RunResult]) -> pd.DataFrame:
    """Where each run's time went (``run.json``'s ``timings``): one row per run with
    the ``STAGE_COLUMNS`` and ``other_s``, what ``duration_s`` (which starts after the
    Ray start-up) holds besides the build, the training calls, the evaluations and the
    checkpoint: writing the tables and reading the action parts' statistics. A run
    still training has no timings yet."""
    rows = []

    for result in results:
        record = registry.read_json(result.ref.folder / "run.json") or {}
        stages = record.get("timings")

        if not stages:
            continue

        row = {c: float(stages.get(c, float("nan"))) for c in STAGE_COLUMNS}
        inside = sum(row[c] for c in STAGE_COLUMNS if c != "ray_init_s")
        row["other_s"] = max(float(record.get("duration_s", inside)) - inside, 0.0)
        rows.append(row | _head(result))

    return pd.DataFrame(rows)


def participant_groups(result: RunResult) -> dict[str, str]:
    """What kind each participant of the run's scenario is: ``battery``, else ``PV``,
    else ``other``. Empty when the run saved only the scenario's file name."""
    scenario = result.settings["scenario"]

    if not isinstance(scenario, dict):
        return {}

    def group(person: dict[str, Any]) -> str:
        if person.get("battery"):
            return "battery"

        return "PV" if any("SGen" in e for e in person.get("owns", [])) else "other"

    return {p["id"]: group(p) for p in scenario.get("participants", [])}


def _groups(result: RunResult, agents: pd.Series) -> list[str]:
    """The group of each of ``agents``."""
    groups = participant_groups(result)

    return [groups.get(agent, UNKNOWN_GROUP) for agent in agents]


def participant_metrics(results: Sequence[RunResult]) -> pd.DataFrame:
    """Every number of ``heldout_agents.csv``, long format: per run, ``policy``,
    ``day``, ``agent``, its ``group``, ``metric`` and ``value``."""
    ids = ["policy", "day", "agent"]
    frames = []

    for result in results:
        frame = result.table("heldout_agents")

        if frame is not None and "policy" in frame:
            numbers = frame.drop(columns=[*ids, "episode", "seed"], errors="ignore")
            numbers = numbers.select_dtypes("number").columns
            long = frame.melt(ids, numbers, var_name="metric", value_name="value")
            frames.append(
                long.assign(**_head(result), group=_groups(result, long.agent))
            )

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def participant_gains(results: Sequence[RunResult]) -> pd.DataFrame:
    """A row per run and participant: ``key``, ``agent``, ``group`` and ``gain``, its
    mean bill minus its mean bill under ``zero`` over the test days."""
    frames = []

    for result in results:
        frame = result.table("heldout_agents")

        if frame is None or not {"policy", "bill"} <= set(frame):
            continue

        bills = frame.pivot_table(index="agent", columns="policy", values="bill")

        if {TRAINED, "zero"} <= set(bills):
            gain = bills[TRAINED] - bills["zero"]
            gains = gain.rename("gain").reset_index()
            frames.append(
                gains.assign(key=result.key, group=_groups(result, gains.agent))
            )

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def trade_table(results: Sequence[RunResult]) -> pd.DataFrame:
    """Every trade of ``heldout_trades.csv.gz``, a row per run and trade, with
    ``band``, a peer trade's place between the step's feed-in tariff (0) and utility
    price (1). Empty for runs without the table."""
    step = ["policy", "episode", "step"]
    frames = []

    for result in results:
        trades, steps = result.table("heldout_trades"), result.table("heldout_steps")

        if trades is None or steps is None:
            continue

        tariffs = steps[[*step, "feed_in_tariff", "utility_price"]]
        found = trades.merge(tariffs, on=step, how="left")
        low, high = found.pop("feed_in_tariff"), found.pop("utility_price")
        band = (found.price - low) / (high - low)
        found["band"] = band.where(found.stage < 3)
        frames.append(found.assign(**_head(result)))

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def participant_days(result: RunResult, value: str = "return") -> pd.DataFrame:
    """One run, per test day and participant (``heldout_agents.csv``): ``value`` for
    each policy and ``trained_minus_<baseline>``. Empty without the table."""
    frame = result.table("heldout_agents")

    if frame is None or value not in frame:
        return pd.DataFrame()

    wide = frame.pivot_table(
        index=["day", "agent"], columns="policy", values=value
    ).reset_index()

    for baseline in BASELINES:
        if TRAINED in wide and baseline in wide:
            wide[f"trained_minus_{baseline}"] = wide[TRAINED] - wide[baseline]

    return wide


# The held-out tables the indicators are computed from (``indicators.day_table``).
INDICATOR_TABLES = (
    "heldout_episodes",
    "heldout_agents",
    "heldout_steps",
    "heldout_agent_steps",
    "heldout_trades",
)


# Policies older runs played on the test days that the results no longer show: the
# money ceiling (``ceiling.py``) took the random policy's place as the outer reference.
HIDDEN_POLICIES = ("random",)


def _scenario(folder: Path) -> Optional[dict]:
    """The run's ``scenario.json``, or None."""
    path = folder / "scenario.json"

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@_latest(DAY_PATHS, DAY_MB)
def _day_table(folder: str, stamp: tuple) -> Optional[pd.DataFrame]:
    """One run's indicators, long format, with the money ceiling as a policy;
    ``stamp`` says its tables are unchanged."""
    from core.runner.ceiling import alone_days, ceiling_days, day_references

    tables = [_table(_table_path(Path(folder), n)) for n in INDICATOR_TABLES]
    tables = [
        t[~t.policy.isin(HIDDEN_POLICIES)] if t is not None and "policy" in t else t
        for t in tables
    ]

    if tables[0] is None or tables[1] is None or "bill" not in tables[1]:
        return None

    scenario = _scenario(Path(folder))

    try:
        top = ceiling_days(tables[3], tables[2], scenario)
        alone = alone_days(tables[3], tables[2], scenario)
        by_day = day_references(tables[3], tables[2], scenario)
    except (ValueError, KeyError):  # tables or a scenario it cannot read
        top = alone = by_day = None

    days = indicators.day_table(
        *tables, ceiling=top, alone=alone, day_references=by_day
    ).reset_index()
    long = days.melt(indicators.KEYS, var_name="indicator")

    # The references play no market: keep only what they have.
    reference = long.policy.isin([indicators.CEILING, indicators.NON_P2P])
    return long[~reference | long.value.notna()]


def _factors(result: RunResult) -> dict[str, Any]:
    """What the run was, as the columns ``indicators.FACTORS`` name."""
    settings = result.settings
    scenario = settings["scenario"] if isinstance(settings["scenario"], dict) else {}
    grid, env = scenario.get("grid", {}), settings["env_config"] or {}
    dso, people = scenario.get("dso", {}), scenario.get("participants", [])

    return {
        "reward": env.get("reward") or "bill",
        "observation": env.get("observation") or "paper",
        "prices": _prices_name(dso.get("prices")),
        "peer_charge": dso.get("peer_charge_kwh", 0.0),
        "network": grid.get("code"),
        "grid_method": grid.get("method"),
        "test_days": _days(settings["test_days"]),
        "participants": len(people),
        "batteries": sum(bool(p.get("battery")) for p in people),
    }


def _prices_name(prices: Any) -> Optional[str]:
    """Prices as one name: the file's, the flat tariffs, or a series' own digest."""
    if prices is None or isinstance(prices, str):
        return prices

    if flat_prices(prices):
        return f"flat {prices['utility']:g} / {prices['feed_in']:g}"

    return "series " + hashlib.sha1(_same(prices).encode()).hexdigest()[:6]


def day_indicators(results: Sequence[RunResult]) -> pd.DataFrame:
    """Every indicator of every run with held-out tables: a row per run, policy, test
    day and indicator, with ``value`` and what the run was."""
    frames = []

    for result in results:
        files = [_table_path(result.ref.folder, n) for n in INDICATOR_TABLES]
        files.append(result.ref.folder / "scenario.json")
        stamp = tuple(p.stat().st_mtime_ns if p.is_file() else 0 for p in files)
        days = _day_table(str(result.ref.folder), stamp)

        if days is not None:
            frames.append(days.assign(**_head(result), **_factors(result)))

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def differing_settings(
    settings: Sequence[dict[str, Any]], keys: Optional[Sequence[str]] = None
) -> list[str]:
    """The settings (all, or only ``keys``) whose values are not the same in every
    one of ``settings`` (``RunResult.settings``)."""
    keys = keys or sorted({k for s in settings for k in s})
    return [k for k in keys if len({_same(s.get(k)) for s in settings}) > 1]


def _same(value: Any) -> str:
    """A value as text that is equal for equal values (dict order ignored)."""
    return json.dumps(value, sort_keys=True, default=str)
