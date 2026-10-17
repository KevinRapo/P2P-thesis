"""An experiment: a JSON file that says which runs to train.

``experiments/<name>.json`` describes a grid of runs (algorithms x paradigms x
seeds x variants) on one environment. ``Experiment.expand()`` turns it into one
``RunSpec`` per run; ``RunSpec.run()`` builds the ``core.rl.Run`` to train.

Importing this module is cheap (no Ray, torch or pandapower): the environment
class and ``core.rl`` are imported only when a run is built.

Fields of the JSON (all but ``scenario`` and the grid axes are optional)::

    {
      "name": "sac_alpha",              default: the file's name
      "description": "free text",
      "env": "market",                  or "module:Class"
      "scenario": "scenarios/validate_market.json",   relative to the repo root
      "train_days": {"from": "2016-06-01", "to": "2016-06-30"},   or a list
      "test_days":  {"from": "2016-07-01", "to": "2016-07-14"},   held-out days
      "env_config": {},                 extra environment settings
      "algorithms": ["sac"], "paradigms": ["dtde"], "seeds": [0],
      "variants": {"a1": {"initial_alpha": 1.0}},   name -> training overrides
      "budget": 24000,                  environment steps; int or {algorithm: int}
      "eval_every": 6000,               int or {algorithm: int}, or instead
      "eval_points": 4,                 number of evaluations, eval_every =
                                        budget // eval_points (give one of the two)
      "eval_episodes": 10,
      "heldout_seeds": 14,              a count (seeds 2000, 2001, ...) or a list;
                                        default: one per test day
      "training": {"sac": {...}},       overrides per algorithm; a variant's
                                        overrides are merged on top
      "model": {},                      network overrides
      "max_parallel": 3, "torch_threads": 1,
      "resources": {"cpus": 4, "mem_gb": 4, "minutes": 120},
                                        per run on a SLURM cluster (the defaults
                                        shown; unknown keys are refused)
      "test": {"budget": 500}           changes to the test profile, see below
    }

Evaluation points: the trainer always evaluates at step 0 (the untrained policy and
the baselines) and at the end of the budget; ``eval_every`` / ``eval_points`` add
the evaluations in between (``eval_points`` counts the final one: 4 points on a
budget of 24000 evaluate at 6000, 12000, 18000 and 24000). Neither: only at the
end.

Test profile: ``Experiment.test_version()`` is the smallest version of the same
experiment, to prove the pipeline (start, train, evaluate, write the results), not
to train. It keeps the scenario, environment, algorithms, paradigms, variants and
settings, and takes the first seed, the first train day and test day, a budget that
reaches learning (``Experiment.test_budget``: one training batch, and for SAC also its
warm-up, so the test run really updates the networks), only the final evaluation (one
episode, one held-out seed), 15 minutes per run and the name ``<name>--test``. The ``test`` block changes any of these: ``seeds`` (a
list), ``train_days`` and ``test_days`` (a number of days), ``budget`` (an int or
``{algorithm: int}``), ``eval_episodes``, ``heldout_seeds`` and ``resources``
(merged over the test defaults).
"""

from __future__ import annotations

import copy
import importlib
import json
from dataclasses import asdict, dataclass, field, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

from core import settings as machine

REPO = Path(__file__).resolve().parents[2]

# Kept in step with core.rl.config (a test compares them): importing the enums from
# there would load Ray and torch just to read a status.
ALGORITHMS = ("ppo", "appo", "sac")
PARADIGMS = ("ctce", "ctde", "dtde")
MARKET_ENVS = ("market", "core.env:MarketEnv", "core.env.market_env:MarketEnv")
HELDOUT_SEED_START = 2000
PROFILES = ("full", "test")
# Per run on a SLURM cluster; ``resources`` in the spec overrides these.
RESOURCE_DEFAULTS = {"cpus": 4, "mem_gb": 4, "minutes": 120}
# What the test profile uses where the ``test`` block says nothing.
TEST_MINUTES = 15
TEST_DEFAULT_BUDGET = 100
# RLlib's own default of ``num_steps_sampled_before_learning_starts`` for SAC in the
# installed version: SAC samples this many steps before its first update.
RLLIB_SAC_WARMUP = 1500
TEST_WARMUP_MARGIN = 100  # steps beyond the warm-up, so learning happens
TEST_KEYS = (
    "seeds",
    "train_days",
    "test_days",
    "budget",
    "eval_episodes",
    "heldout_seeds",
    "resources",
)


class SpecError(ValueError):
    """The experiment file is wrong; the message says what to change."""


# --------------------------------------------------------------------------------------
# Where things are
# --------------------------------------------------------------------------------------
def runs_root() -> Path:
    """The folder with the experiments: the setting ``MARLEM_RUNS``
    (``core/settings.py``) or ``<repo>/runs``."""
    return Path(machine.get("MARLEM_RUNS") or REPO / "runs")


def load_env_class(env: str) -> type:
    """The environment class: ``"market"`` or a ``"module:Class"`` path."""
    if env in MARKET_ENVS:
        from core.env import MarketEnv

        return MarketEnv
    module, _, name = env.partition(":")
    obj: Any = importlib.import_module(module)
    for part in name.split("."):
        obj = getattr(obj, part)
    return obj


# --------------------------------------------------------------------------------------
# One run of the grid
# --------------------------------------------------------------------------------------
@dataclass
class RunSpec:
    """One run of an experiment: everything ``core.rl.Run`` needs."""

    name: str
    algorithm: str
    paradigm: str
    seed: int
    variant: Optional[str]
    env: str
    env_config: dict
    budget: int
    eval_every: int
    eval_episodes: int
    training: dict
    model: dict
    out_dir: Path
    index: int = 0

    def run(self):
        """The ``core.rl.Run`` to train (imports ``core.rl``: slow)."""
        from core.rl.train import Run

        return Run(
            algorithm=self.algorithm,
            paradigm=self.paradigm,
            env_class=load_env_class(self.env),
            env_config=dict(self.env_config),
            budget=self.budget,
            seed=self.seed,
            eval_every=self.eval_every,
            eval_episodes=self.eval_episodes,
            training=dict(self.training),
            model=dict(self.model),
            out_dir=self.out_dir,
        )


# --------------------------------------------------------------------------------------
# The experiment file
# --------------------------------------------------------------------------------------
@dataclass
class Experiment:
    """An experiment as written in ``experiments/<name>.json`` (see the module)."""

    name: str
    algorithms: list[str]
    paradigms: list[str]
    seeds: list[int]
    budget: int | dict[str, int]
    scenario: Optional[str] = None
    env: str = "market"
    train_days: list[str] = field(default_factory=list)
    test_days: list[str] = field(default_factory=list)
    env_config: dict = field(default_factory=dict)
    variants: dict[str, dict] = field(default_factory=dict)
    eval_every: int | dict[str, int] | None = None
    eval_points: int | dict[str, int] | None = None
    eval_episodes: int = 10
    heldout_seeds: int | list[int] | None = None
    training: dict[str, dict] = field(default_factory=dict)
    model: dict = field(default_factory=dict)
    max_parallel: int = 3
    torch_threads: int = 1
    resources: dict = field(default_factory=dict)
    test: dict = field(default_factory=dict)
    description: str = ""

    # --- Loading ----------------------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path, check_files: bool = True) -> "Experiment":
        """Read and validate an experiment file; the name defaults to its stem."""
        path = Path(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise SpecError(f"experiment file not found: {path}") from None
        except json.JSONDecodeError as error:
            raise SpecError(f"{path}: not valid JSON ({error})") from None
        return cls.from_dict(data, default_name=path.stem, check_files=check_files)

    @classmethod
    def from_dict(
        cls, data: dict, default_name: str = "experiment", check_files: bool = True
    ) -> "Experiment":
        if not isinstance(data, dict):
            raise SpecError("an experiment file holds one JSON object")
        known = set(cls.__dataclass_fields__)
        unknown = sorted(set(data) - known)
        if unknown:
            raise SpecError(
                f"unknown field(s) {unknown}; the fields are {sorted(known)}"
            )
        data = dict(data)
        data.setdefault("name", default_name)
        for key in ("train_days", "test_days"):
            data[key] = _days(data.get(key), key)
        for key in ("algorithms", "paradigms", "seeds", "budget"):
            if key not in data:
                raise SpecError(f"missing field '{key}'")
        try:
            experiment = cls(**data)
        except TypeError as error:
            raise SpecError(str(error)) from None
        experiment.validate(check_files=check_files)
        return experiment

    # --- Validation -------------------------------------------------------------------
    def validate(self, check_files: bool = True) -> None:
        name = self.name
        if not name or any(c in name for c in '/\\:*?"<>| ') or name.startswith("."):
            raise SpecError(f"name {name!r} must be a plain folder name (no spaces)")
        for axis, allowed, values in (
            ("algorithms", ALGORITHMS, self.algorithms),
            ("paradigms", PARADIGMS, self.paradigms),
        ):
            if not isinstance(values, list) or not values:
                raise SpecError(f"'{axis}' must be a non-empty list")
            bad = [v for v in values if v not in allowed]
            if bad:
                raise SpecError(f"unknown {axis} {bad}; choose from {list(allowed)}")
            if len(set(values)) != len(values):
                raise SpecError(f"'{axis}' has duplicates")
        if (
            not isinstance(self.seeds, list)
            or not self.seeds
            or not all(
                isinstance(s, int) and not isinstance(s, bool) for s in self.seeds
            )
            or len(set(self.seeds)) != len(self.seeds)
        ):
            raise SpecError("'seeds' must be a non-empty list of distinct integers")
        if not isinstance(self.variants, dict) or not all(
            isinstance(v, dict) for v in self.variants.values()
        ):
            raise SpecError("'variants' maps a name to a dict of training overrides")
        for variant in self.variants:
            if not variant or any(c in variant for c in '/\\:*?"<>| '):
                raise SpecError(f"variant name {variant!r} must be a plain word")
        if not isinstance(self.training, dict) or not set(self.training) <= set(
            ALGORITHMS
        ):
            raise SpecError(
                "'training' maps an algorithm name to its overrides, e.g. "
                '{"ppo": {"lr": 0.0003}}; keys must be among ' + str(list(ALGORITHMS))
            )
        if self.eval_every is not None and self.eval_points is not None:
            raise SpecError("give 'eval_every' or 'eval_points', not both")
        for algorithm in self.algorithms:
            budget = self._per_algorithm(self.budget, algorithm, "budget")
            if not isinstance(budget, int) or budget <= 0:
                raise SpecError(f"budget for {algorithm} must be a positive integer")
            for key in ("eval_every", "eval_points"):
                value = self._per_algorithm(getattr(self, key), algorithm, key, True)
                if value is not None and (not isinstance(value, int) or value < 0):
                    raise SpecError(f"'{key}' for {algorithm} must be an integer >= 0")
        if self.max_parallel < 1 or self.torch_threads < 1 or self.eval_episodes < 1:
            raise SpecError("max_parallel, torch_threads, eval_episodes must be >= 1")
        if self.is_market and not self.scenario:
            raise SpecError("the market environment needs a 'scenario' file")
        if self.scenario and check_files and not self.scenario_path.is_file():
            raise SpecError(
                f"scenario file not found: {self.scenario_path} "
                "('scenario' is relative to the repository root)"
            )
        if self.env not in MARKET_ENVS and ":" not in self.env:
            raise SpecError(f"env {self.env!r} must be 'market' or 'module:Class'")
        _check_resources(self.resources, "resources")
        self._validate_test_block()

    def _validate_test_block(self) -> None:
        test = self.test
        if not isinstance(test, dict):
            raise SpecError(f"'test' maps {list(TEST_KEYS)} to settings")
        unknown = sorted(set(test) - set(TEST_KEYS))
        if unknown:
            raise SpecError(f"unknown 'test' key(s) {unknown}; use {list(TEST_KEYS)}")
        if not isinstance(test.get("seeds", []), list):
            raise SpecError("'test.seeds' is a list of seeds")
        for key in ("train_days", "test_days"):
            count = test.get(key, 1)
            if isinstance(count, bool) or not isinstance(count, int) or count < 1:
                raise SpecError(f"'test.{key}' is a number of days (an integer >= 1)")
        _check_resources(test.get("resources", {}), "test.resources")
        if test:  # the rest is checked on the version it makes
            try:
                self.test_version()
            except SpecError as error:
                raise SpecError(f"'test' block: {error}") from None

    @staticmethod
    def _per_algorithm(value, algorithm: str, key: str, optional: bool = False):
        if isinstance(value, dict):
            if algorithm not in value:
                if optional:
                    return None
                raise SpecError(f"'{key}' has no entry for algorithm '{algorithm}'")
            return value[algorithm]
        return value

    # --- Derived ----------------------------------------------------------------------
    @property
    def is_market(self) -> bool:
        return self.env in MARKET_ENVS

    @property
    def scenario_path(self) -> Path:
        return (REPO / self.scenario).resolve()

    @property
    def run_resources(self) -> dict:
        """What one run asks of a SLURM cluster: ``cpus``, ``mem_gb`` and ``minutes``,
        the spec's ``resources`` over the defaults."""
        return RESOURCE_DEFAULTS | self.resources

    def heldout_seed_list(self) -> list[int]:
        """Seeds of the held-out evaluation: a given list, a count from 2000, or one
        per test day."""
        if isinstance(self.heldout_seeds, list):
            return [int(s) for s in self.heldout_seeds]
        count = self.heldout_seeds or len(self.test_days) or 14
        return list(range(HELDOUT_SEED_START, HELDOUT_SEED_START + int(count)))

    def heldout_config(self) -> dict:
        """The environment config of the held-out evaluation (test days)."""
        config: dict = {"scenario": str(self.scenario_path), "days": self.test_days}
        return config | self.env_config

    # --- Writing and profiles ---------------------------------------------------------
    def to_dict(self) -> dict:
        """The experiment as a JSON-serialisable dict that ``from_dict`` loads back to
        an equal ``Experiment``; days are written out as lists of ISO dates."""
        return asdict(self)

    def with_profile(self, profile: str) -> "Experiment":
        """The experiment as it runs in a profile: ``"full"`` (as written) or
        ``"test"`` (``test_version()``)."""
        if profile == "full":
            return self
        if profile == "test":
            return self.test_version()
        raise SpecError(f"unknown profile {profile!r}; choose from {list(PROFILES)}")

    def test_budget(self, algorithm: str) -> int:
        """The test profile's budget for ``algorithm``: enough environment steps for
        learning to happen, from the settings each variant really uses.

        For each variant (or the algorithm's ``training`` settings alone, without
        variants) the settings are merged as in ``expand``; the budget is one training
        batch (``train_batch_size_per_learner``, else ``TEST_DEFAULT_BUDGET``), or, if
        the algorithm has a warm-up before it learns, the warm-up plus
        ``TEST_WARMUP_MARGIN``. The warm-up is
        ``num_steps_sampled_before_learning_starts``, by default ``RLLIB_SAC_WARMUP``
        for SAC and none for the others. The largest over the variants wins.
        """
        base = self.training.get(algorithm, {})
        default_warmup = RLLIB_SAC_WARMUP if algorithm == "sac" else 0
        budgets = []
        for overrides in list(self.variants.values()) or [{}]:
            settings = base | overrides
            batch = settings.get("train_batch_size_per_learner") or TEST_DEFAULT_BUDGET
            warmup = settings.get(
                "num_steps_sampled_before_learning_starts", default_warmup
            )
            budgets.append(max(batch, warmup + TEST_WARMUP_MARGIN) if warmup else batch)
        return max(budgets)

    def test_version(self) -> "Experiment":
        """The smallest version of this experiment, to prove the pipeline (see the
        module); each default is overridden by the ``test`` block."""
        test = self.test
        budget = test.get(
            "budget",
            {algorithm: self.test_budget(algorithm) for algorithm in self.algorithms},
        )
        resources = (
            self.run_resources | {"minutes": TEST_MINUTES} | test.get("resources", {})
        )
        description = f"Test version of {self.name}"
        if self.description:
            description += f": {self.description}"
        version = replace(
            copy.deepcopy(self),
            name=f"{self.name}--test",
            seeds=list(test.get("seeds", self.seeds[:1])),
            train_days=self.train_days[: test.get("train_days", 1)],
            test_days=self.test_days[: test.get("test_days", 1)],
            budget=budget,
            eval_every=None,
            eval_points=None,
            eval_episodes=test.get("eval_episodes", 1),
            heldout_seeds=test.get("heldout_seeds", 1),
            resources=dict(resources),
            test={},
            description=description,
        )
        version.validate(check_files=False)  # the scenario is the original's
        return version

    # --- Expansion --------------------------------------------------------------------
    def expand(self, exp_dir: Optional[Path] = None) -> list[RunSpec]:
        """One ``RunSpec`` per run of the grid; run folders are inside ``exp_dir``
        (default: ``<runs root>/<name>``)."""
        exp_dir = Path(exp_dir) if exp_dir else runs_root() / self.name
        variants = self.variants or {None: {}}
        specs: list[RunSpec] = []
        for algorithm in self.algorithms:
            budget = self._per_algorithm(self.budget, algorithm, "budget")
            every = self._per_algorithm(self.eval_every, algorithm, "eval_every", True)
            points = self._per_algorithm(
                self.eval_points, algorithm, "eval_points", True
            )
            if every is None:
                every = budget // points if points else 0
            for paradigm in self.paradigms:
                for variant, overrides in variants.items():
                    for seed in self.seeds:
                        name = f"{algorithm}_{paradigm}_s{seed}"
                        if variant is not None:
                            name += f"_{variant}"
                        specs.append(
                            RunSpec(
                                name=name,
                                algorithm=algorithm,
                                paradigm=paradigm,
                                seed=seed,
                                variant=variant,
                                env=self.env,
                                env_config=self._env_config(seed),
                                budget=budget,
                                eval_every=every,
                                eval_episodes=self.eval_episodes,
                                training=dict(self.training.get(algorithm, {}))
                                | dict(overrides),
                                model=dict(self.model),
                                out_dir=exp_dir / name,
                                index=len(specs),
                            )
                        )
        return specs

    def _env_config(self, seed: int) -> dict:
        config: dict = {}
        if self.scenario:
            config["scenario"] = str(self.scenario_path)
        if self.train_days:
            config["days"] = list(self.train_days)
        config["seed"] = seed
        return config | self.env_config


# --------------------------------------------------------------------------------------
# Resources
# --------------------------------------------------------------------------------------
def _check_resources(value, where: str) -> None:
    """``value`` maps some of ``cpus``, ``mem_gb`` and ``minutes`` to positive numbers
    (``cpus`` and ``minutes`` whole)."""
    if not isinstance(value, dict):
        raise SpecError(f"'{where}' maps {sorted(RESOURCE_DEFAULTS)} to numbers")
    unknown = sorted(set(value) - set(RESOURCE_DEFAULTS))
    if unknown:
        raise SpecError(
            f"unknown '{where}' key(s) {unknown}; use {sorted(RESOURCE_DEFAULTS)}"
        )
    for key, number in value.items():
        kinds = (int, float) if key == "mem_gb" else int
        if isinstance(number, bool) or not isinstance(number, kinds) or number <= 0:
            raise SpecError(
                f"'{where}.{key}' must be a positive "
                f"{'number' if key == 'mem_gb' else 'integer'}"
            )


# --------------------------------------------------------------------------------------
# Days
# --------------------------------------------------------------------------------------
def _days(value, key: str) -> list[str]:
    """A list of ISO dates, or ``{"from": ..., "to": ...}`` (both included)."""
    if value is None:
        return []
    try:
        if isinstance(value, dict):
            if set(value) != {"from", "to"}:
                raise SpecError(f"'{key}' as a range needs exactly 'from' and 'to'")
            first, last = date.fromisoformat(value["from"]), date.fromisoformat(
                value["to"]
            )
            if last < first:
                raise SpecError(f"'{key}': 'to' is before 'from'")
            return [
                (first + timedelta(days=i)).isoformat()
                for i in range((last - first).days + 1)
            ]
        if isinstance(value, list):
            return [date.fromisoformat(d).isoformat() for d in value]
    except (ValueError, TypeError) as error:
        raise SpecError(f"'{key}': bad date ({error}); use YYYY-MM-DD") from None
    raise SpecError(f"'{key}' must be a list of dates or {{'from': ..., 'to': ...}}")
