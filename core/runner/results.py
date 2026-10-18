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
The spread over seeds comes from separate runs (``seed_groups``), never from the
days or the participants of one run.

    find_runs()                  every run of this PC and of the synced mirrors
    load_runs(refs)              their ``RunResult``: settings, state, tables
    overview(results)            one row per run: settings, state, held-out scores
    learning_curves(results)     evaluation return over environment steps
    training_curves(results)     training return over environment steps
    heldout_days(results)        per run and test day: each policy's team return
                                 and the trained policy minus each baseline
    participant_days(result)     one run, per test day and participant: the same
    seed_groups(results)         per configuration over its seeds: mean, spread,
                                 number of seeds, and the settings that differ
    differing_settings(results)  the settings that are not the same in all runs
                                 (their full saved values)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

import pandas as pd

from core.runner import registry
from core.runner.registry import RunState
from core.runner.spec import REPO, runs_root

LOCAL = "local"
BASELINES = ("zero", "net_position")
TRAINED = "trained"
# A run folder's name: <algorithm>_<paradigm>_s<seed>[_<variant>] (``spec.expand``).
_RUN_NAME = re.compile(r"^(?P<algorithm>[a-z]+)_(?P<paradigm>[a-z]+)_s(?P<seed>\d+)")
# What a configuration is, for ``seed_groups``: everything but the seed.
GROUP_BY = ("target", "experiment", "algorithm", "paradigm", "variant")
# Settings that must match for runs to be compared as one configuration: their full
# saved values (the scenario's contents, every day), not their labels.
COMPARED = (
    "scenario",
    "train_days",
    "test_days",
    "budget",
    "overrides",
    "model",
    "results_detail",
    "commit",
)


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


def find_runs(where: Optional[dict[str, Path]] = None) -> list[RunRef]:
    """Every run folder of every source (default ``sources()``), by target,
    experiment and run name. A mirror inside the runs root is not read twice."""
    where = where or sources()
    mirrors = {Path(p).resolve() for t, p in where.items() if t != LOCAL}
    found = []
    for target, root in where.items():
        root = Path(root)
        for experiment in registry.experiments(root):
            folder = root / experiment
            if folder.resolve() in mirrors and target == LOCAL:
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
        settings: What it was, as saved: ``algorithm``, ``paradigm``, ``seed``,
            ``variant``, ``test`` (a test-profile run), ``scenario`` (its contents,
            or its file name in older runs), ``train_days`` and ``test_days`` (every
            day), ``budget``, ``overrides`` (the training settings it ran with),
            ``model``, ``results_detail``, ``commit``, ``uncommitted``; None where
            the files do not say. Compare these; show ``labels``.
        state: Its ``RunState`` (None if the folder cannot be read as a run).
    """

    ref: RunRef
    settings: dict[str, Any]
    state: Optional[RunState]
    _tables: dict[str, Optional[pd.DataFrame]] = field(default_factory=dict)

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
        shown = {k: v for k, v in settings.items() if k not in ("overrides", "model")}
        return shown | {
            "scenario": scenario,
            "train_days": _days(settings["train_days"]),
            "test_days": _days(settings["test_days"]),
        }

    def has(self, name: str) -> bool:
        """Whether the run has the table ``<name>.csv``, without reading it."""
        return (self.ref.folder / f"{name}.csv").is_file()

    def table(self, name: str) -> Optional[pd.DataFrame]:
        """The run's ``<name>.csv`` (e.g. ``"heldout_episodes"``), None if it has
        none; read once."""
        if name not in self._tables:
            path = self.ref.folder / f"{name}.csv"
            try:
                self._tables[name] = pd.read_csv(path) if path.is_file() else None
            except (OSError, ValueError, pd.errors.EmptyDataError):
                self._tables[name] = None
        return self._tables[name]


def load_run(ref: RunRef) -> RunResult:
    """A run's settings and state, from its folder and its experiment's."""
    record = registry.read_json(ref.folder / "run.json") or {}
    spec = registry.read_json(ref.folder.parent / "experiment.json") or {}
    name = _RUN_NAME.match(ref.run)
    seed = record.get("seed", int(name["seed"]) if name else None)
    variant = None
    if name and len(ref.run) > name.end():
        variant = ref.run[name.end() + 1 :]
    git = record.get("git") or {}
    settings = {
        "algorithm": record.get("algorithm", name["algorithm"] if name else None),
        "paradigm": record.get("paradigm", name["paradigm"] if name else None),
        "seed": seed,
        "variant": variant,
        "test": ref.experiment.endswith("--test"),
        "scenario": spec.get("scenario"),
        "train_days": spec.get("train_days"),
        "test_days": spec.get("test_days"),
        "budget": record.get("budget_env_steps"),
        "overrides": record.get("settings"),
        "model": record.get("model"),
        "results_detail": spec.get("results_detail", "standard"),
        "commit": (git.get("commit") or "")[:8] or None,
        "uncommitted": git.get("uncommitted_changes"),
    }
    return RunResult(ref, settings, registry.run_state(ref.folder))


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


def overview(results: Sequence[RunResult]) -> pd.DataFrame:
    """One row per run: what it was, how far it got, and its held-out team return
    for the trained policy and each baseline (``heldout.csv``)."""
    rows = []
    for result in results:
        state = result.state
        row = _head(result) | {
            "test": result.settings["test"],
            "state": state.state if state else None,
            "env_steps": state.env_steps if state else None,
            "budget": result.settings["budget"],
            "commit": result.settings["commit"],
        }
        heldout = result.table("heldout")
        if heldout is not None and "policy" in heldout:
            scores = heldout.set_index("policy")["team_return_mean"]
            row["participants"] = _agents(heldout)
            for policy in (TRAINED, *BASELINES):
                row[f"heldout_{policy}"] = scores.get(policy)
        rows.append(row)
    return pd.DataFrame(rows)


def learning_curves(results: Sequence[RunResult]) -> pd.DataFrame:
    """Evaluation during training (``evaluation.csv``): one row per run, evaluation
    point and policy, with the team return and its mean per participant."""
    frames = []
    for result in results:
        frame = result.table("evaluation")
        if frame is None:
            continue
        frame = frame[["env_steps", "policy", "team_return_mean"]].copy()
        frame["per_participant"] = frame.team_return_mean / _agents(
            result.table("evaluation")
        )
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


def heldout_days(results: Sequence[RunResult]) -> pd.DataFrame:
    """Per run and test day (``heldout_episodes.csv``): each policy's team return,
    and ``trained_minus_<baseline>``, the paired difference on the same day. A run
    without the per-day table gives one row with its means and no day."""
    rows = []
    for result in results:
        frame = result.table("heldout_episodes")
        if frame is not None:
            days = frame.pivot_table(
                index="day", columns="policy", values="team_return"
            )
            scores = {day: dict(row) for day, row in days.iterrows()}
        else:  # an older run: its means only
            frame = result.table("heldout")
            if frame is None or "policy" not in frame:
                continue
            scores = {None: dict(zip(frame.policy, frame.team_return_mean))}
        for day, score in scores.items():
            row = _head(result) | {"day": day}
            for policy in (TRAINED, *BASELINES):
                row[policy] = score.get(policy)
            for baseline in BASELINES:
                if row[TRAINED] is not None and row[baseline] is not None:
                    row[f"trained_minus_{baseline}"] = row[TRAINED] - row[baseline]
            rows.append(row)
    return pd.DataFrame(rows)


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


def seed_groups(
    results: Sequence[RunResult], by: Sequence[str] = GROUP_BY
) -> pd.DataFrame:
    """Runs of one configuration (``by``: everything but the seed) over their seeds.

    Per group: ``runs``, ``completed``, the ``seeds``; the trained policy's held-out
    team return over the completed seeds (each seed's mean over its test days):
    ``mean``, ``std`` (over seeds, 0 with one), ``min``, ``max``; the mean of
    ``trained_minus_<baseline>``; and ``differs``: the settings of ``COMPARED`` that
    are not the same in all its runs (a group should have none).
    """
    table = overview(results)
    if table.empty:
        return table
    settings = {r.key: r.settings for r in results}
    rows = []
    for values, group in table.groupby(list(by), dropna=False, sort=False):
        done = group[group.state == "completed"]
        trained = done.get(f"heldout_{TRAINED}", pd.Series(dtype=float)).dropna()
        row = dict(zip(by, values if isinstance(values, tuple) else (values,)))
        row |= {
            "runs": len(group),
            "completed": len(done),
            "seeds": sorted(int(s) for s in group.seed.dropna()),
            "mean": trained.mean() if len(trained) else None,
            "std": trained.std(ddof=0) if len(trained) else None,
            "min": trained.min() if len(trained) else None,
            "max": trained.max() if len(trained) else None,
        }
        for baseline in BASELINES:
            column = f"heldout_{baseline}"
            if column in done and len(trained):
                row[f"trained_minus_{baseline}"] = (
                    trained - done.loc[trained.index, column]
                ).mean()
        row["differs"] = differing_settings([settings[k] for k in group.key], COMPARED)
        rows.append(row)
    return pd.DataFrame(rows)


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
