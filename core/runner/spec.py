"""An experiment: a JSON file that says which runs to train.

``config/experiments/<name>.json`` describes a grid of runs (algorithms x paradigms x
seeds x variants) on one environment. ``Experiment.expand()`` turns it into one
``RunSpec`` per run; ``RunSpec.run()`` builds the ``core.rl.Run`` to train.

Importing this module is cheap (no Ray, torch or pandapower): the environment
class and ``core.rl`` are imported only when a run is built.

Fields of the JSON (all but ``scenario`` and the grid axes are optional)::

    {
      "name": "market_ppo",             default: the file's name
      "description": "free text",
      "env": "market",                  or "module:Class"
      "scenario": "config/scenarios/validate_market.json",   relative to the repo root,
                                        or the scenario itself (a JSON object)
      "train_days": {"from": "2016-06-01", "to": "2016-06-30"},   or a list
      "test_periods": {"summer": {"from": "2016-07-01", "to": "2016-07-14"}},
                                        the held-out days: named continuous
                                        periods (a range or a list each), left out
                                        of train_days
      "env_config": {},                 extra environment settings
      "algorithms": ["ppo"], "paradigms": ["dtde"], "seeds": [0],
      "variants": {"lr3": {"training": {"ppo": {"lr": 0.001}}}},   name -> what the
                                        arm overwrites (see Variants)
      "budget": 24000,                  environment steps; int or {algorithm: int}
      "eval_points": 4,                 evaluations during training; int or
                                        {algorithm: int}
      "eval_episodes": 10,
      "results_detail": "standard",     or "detailed": also the held-out
                                        evaluation step by step on trace_days
      "trace_days": 3,                  with "detailed": the first 3 test days, or
                                        a list of test days
      "training": {"ppo": {...}},       overrides per algorithm; a variant's
                                        overrides are merged on top
      "model": {},                      network overrides
      "max_parallel": 3, "torch_threads": 1,
      "num_env_runners": 0,             remote samplers per run; 0 samples locally
      "ray_thread_caps": true,          Ray's thread pools at one thread each
                                        (launch.RAY_THREAD_CAPS); false: Ray's
                                        own sizes, from the node's hardware
      "resources": {"cpus": 4, "mem_gb": 4, "minutes": 120, "node": null},
                                        per run on a SLURM cluster (the defaults
                                        shown; unknown keys are refused); "node":
                                        one node by name ("blackwell1"), null:
                                        any node of the partition
      "test": {"budget": 500}           changes to the test profile, see below
    }

Variants: the file is the base case, and a variant is an arm of it: the fields it
gives overwrite the base (``overwrite``: inside a section only the values it names,
a list as a whole). It may give any field but ``NOT_IN_A_VARIANT``, so that the
grid of runs stays algorithms x paradigms x variants x seeds, e.g.
{"big": {"model": {"fcnet_hiddens": [768, 768]}, "budget": 480000},
"graph": {"scenario": {"grid": {"method": "graph"}}}}. ``scenario`` may also name
another file. ``Experiment.arm`` gives an arm as a complete experiment; a started
experiment saves it as ``experiment_<variant>.json`` and ``scenario_<variant>.json``
in its folder, and the arm's runs read that scenario.

Evaluation points: the trainer always evaluates at step 0 (the untrained policy and
the baselines) and at the end of the budget; ``eval_points`` adds the evaluations in
between and counts the final one: 4 points on a budget of 24000 evaluate at 6000,
12000, 18000 and 24000. Without it: only at the end.

Held-out evaluation: after training, the trained policy and the baselines play every
test day once, in order (``Experiment.heldout_episodes``: seeds 2000, 2001, ...).
Inside a test period the batteries and reputations carry from day to day, and every policy
starts each period from the scenario's initial state (``heldout_options``). Its
results are kept per day and participant (``launch.py``); with ``results_detail``
``"detailed"`` the days of ``trace_days`` are also kept step by step.

Test profile: ``Experiment.test_version()`` is the smallest version of the same
experiment, to prove the pipeline (start, train, evaluate, write the results), not
to train. It keeps the scenario, environment, algorithms, paradigms, variants and
settings, and takes the first seed, the first train day and test day, a budget that
reaches learning (``Experiment.test_budget``: one training batch, so the test run
really updates the networks), only the final evaluation (one
episode; the held-out evaluation on its one test day), 15 minutes per run and the name
``<name>--test``. The ``test`` block changes any of these: ``seeds`` (a list),
``train_days`` and ``test_days`` (a number of days), ``budget`` (an int or
``{algorithm: int}``), ``eval_episodes`` and ``resources`` (merged over the test
defaults). Traced days that the test version has no longer are left out.

Inputs of a started experiment: an experiment is started as ``resolve`` gives it, with
the scenario file read into ``scenario`` and its price file into the scenario's
``dso.prices`` (``Experiment.inline_scenario``). The
``experiment.json`` of its folder then holds every input of its runs, the scenario
included, and the runs read the copy ``scenario.json`` next to it (``SCENARIO_FILE``),
not the file in ``config/scenarios/``. So an experiment can be sent to a cluster as one JSON
object, without its files being in the cluster's checkout, and a later change to
the scenario or price file does not change an experiment already started.
"""

from __future__ import annotations

import copy
import importlib
import json
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from core import settings as machine
from core.config.scenario import GridSetup, load_prices
from core.env_defaults import MARKET_ENV_CONFIG, OBSERVATION_NAMES, REWARD_NAMES

REPO = Path(__file__).resolve().parents[2]

# Kept in step with core.rl.config (a test compares them): importing the enums from
# there would load Ray and torch just to read a status.
ALGORITHMS = ("ppo",)  # V2: PPO only
PARADIGMS = ("ctce", "ctde", "dtde")
MARKET_ENVS = ("market", "core.env:MarketEnv", "core.env.market_env:MarketEnv")
HELDOUT_SEED_START = 2000
PROFILES = ("full", "test")
RESULTS_DETAILS = ("standard", "detailed")
TRACE_DAYS = 3  # the default of ``trace_days``
# The scenario of a started experiment, in its folder (see the module).
SCENARIO_FILE = "scenario.json"
# What a variant cannot overwrite: the axes of the grid of runs, and what belongs to
# the experiment as a whole.
NOT_IN_A_VARIANT = (
    "name",
    "description",
    "algorithms",
    "paradigms",
    "seeds",
    "variants",
    "test_days",
    "max_parallel",
    "resources",
    "test",
)
# What a variant keeps out of the test version, which is the smallest run of any arm.
NOT_IN_A_TEST_VARIANT = (
    "train_days",
    "test_periods",
    "budget",
    "eval_points",
    "eval_episodes",
    "trace_days",
)
# Per run on a SLURM cluster; ``resources`` in the spec overrides these.
RESOURCE_DEFAULTS = {"cpus": 4, "mem_gb": 4, "minutes": 120, "node": None}
# What the test profile uses where the ``test`` block says nothing.
TEST_MINUTES = 15
TEST_DEFAULT_BUDGET = 100
TEST_KEYS = (
    "seeds",
    "train_days",
    "test_days",
    "budget",
    "eval_episodes",
    "resources",
)
_GONE = (
    "'heldout_seeds' is gone: the held-out evaluation plays every test day once "
    "(seeds 2000, 2001, ...); remove it"
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
    num_env_runners: int = 0

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
            num_env_runners=self.num_env_runners,
            out_dir=self.out_dir,
        )


# --------------------------------------------------------------------------------------
# The experiment file
# --------------------------------------------------------------------------------------
@dataclass
class Experiment:
    """An experiment as written in ``config/experiments/<name>.json`` (see the module)."""

    name: str
    algorithms: list[str]
    paradigms: list[str]
    seeds: list[int]
    budget: int | dict[str, int]
    scenario: str | dict | None = None
    env: str = "market"
    train_days: list[str] = field(default_factory=list)
    test_days: list[str] = field(default_factory=list)  # from test_periods
    test_periods: dict[str, list[str]] = field(default_factory=dict)
    env_config: dict = field(default_factory=dict)
    variants: dict[str, dict] = field(default_factory=dict)
    eval_points: int | dict[str, int] | None = None
    eval_episodes: int = 10
    results_detail: str = "standard"
    trace_days: int | list[str] = TRACE_DAYS
    training: dict[str, dict] = field(default_factory=dict)
    model: dict = field(default_factory=dict)
    max_parallel: int = 3
    torch_threads: int = 1
    num_env_runners: int = 0
    ray_thread_caps: bool = True
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

        if "heldout_seeds" in data or "heldout_seeds" in (data.get("test") or {}):
            raise SpecError(_GONE)

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

        data["test_periods"] = _periods(data)
        held_out = [d for days in data["test_periods"].values() for d in days]

        if data["test_days"] not in ([], held_out):
            raise SpecError("'test_days' is gone: give the days as 'test_periods'")

        data["test_days"] = held_out
        data["train_days"] = [d for d in data["train_days"] if d not in held_out]

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
            raise SpecError("'variants' maps a name to what the arm overwrites")

        for variant, changes in self.variants.items():
            if not variant or any(c in variant for c in '/\\:*?"<>| '):
                raise SpecError(f"variant name {variant!r} must be a plain word")

            allowed = set(self.__dataclass_fields__) - set(NOT_IN_A_VARIANT)
            unknown = sorted(set(changes) - allowed)

            if unknown:
                raise SpecError(
                    f"variant {variant!r} cannot overwrite {unknown}; "
                    f"it may give {sorted(allowed)}"
                )

            if check_files or not isinstance(self.scenario, str):
                self.arm(variant)

        self._check_env_config()

        if not isinstance(self.training, dict) or not set(self.training) <= set(
            ALGORITHMS
        ):
            raise SpecError(
                "'training' maps an algorithm name to its overrides, e.g. "
                '{"ppo": {"lr": 0.0003}}; keys must be among ' + str(list(ALGORITHMS))
            )

        for algorithm in self.algorithms:
            budget = self._per_algorithm(self.budget, algorithm, "budget")
            if not isinstance(budget, int) or budget <= 0:
                raise SpecError(f"budget for {algorithm} must be a positive integer")
            points = self._per_algorithm(
                self.eval_points, algorithm, "eval_points", True
            )
            if points is not None and (not isinstance(points, int) or points < 0):
                raise SpecError(
                    f"'eval_points' for {algorithm} must be an integer >= 0"
                )

        if self.max_parallel < 1 or self.torch_threads < 1 or self.eval_episodes < 1:
            raise SpecError("max_parallel, torch_threads, eval_episodes must be >= 1")

        if type(self.num_env_runners) is not int or self.num_env_runners < 0:
            raise SpecError("num_env_runners must be an integer >= 0")

        if type(self.ray_thread_caps) is not bool:
            raise SpecError("ray_thread_caps must be true or false")

        if self.is_market and not self.scenario:
            raise SpecError("the market environment needs a 'scenario'")

        if self.scenario is not None and not isinstance(self.scenario, (str, dict)):
            raise SpecError(
                "'scenario' is a file relative to the repository root, or the "
                "scenario itself (a JSON object)"
            )

        if (
            isinstance(self.scenario, str)
            and check_files
            and not self.scenario_path.is_file()
        ):
            raise SpecError(
                f"scenario file not found: {self.scenario_path} "
                "('scenario' is relative to the repository root)"
            )

        if self.env not in MARKET_ENVS and ":" not in self.env:
            raise SpecError(f"env {self.env!r} must be 'market' or 'module:Class'")

        _check_resources(self.resources, "resources")
        self._validate_results()
        self._validate_test_block()

    def _validate_results(self) -> None:
        if self.results_detail not in RESULTS_DETAILS:
            raise SpecError(
                f"'results_detail' is one of {list(RESULTS_DETAILS)}, "
                f"not {self.results_detail!r}"
            )
        days = self.trace_days
        if isinstance(days, list):
            missing = [d for d in days if d not in self.test_days]
            if missing:
                raise SpecError(f"'trace_days' {missing} are not test days")
        elif isinstance(days, bool) or not isinstance(days, int) or days < 1:
            raise SpecError("'trace_days' is a number of test days (>= 1) or a list")

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

    def _check_env_config(self) -> None:
        """A market's ``env_config`` holds only its known settings: a misspelt one
        would otherwise do nothing."""
        if not isinstance(self.env_config, dict):
            raise SpecError("'env_config' must be a dict")

        unknown = sorted(set(self.env_config) - set(MARKET_ENV_CONFIG))

        if self.is_market and unknown:
            raise SpecError(
                f"unknown env_config setting(s) {unknown}; "
                f"the settings are {sorted(MARKET_ENV_CONFIG)}"
            )

        reward = self.env_config.get("reward") or "bill"

        if self.is_market and reward not in REWARD_NAMES:
            raise SpecError(
                f"unknown reward {reward!r}; choose from {list(REWARD_NAMES)}"
            )

        if reward == "salazar" and not self.env_config.get("grid_capacity_kwh"):
            raise SpecError("the 'salazar' reward needs 'grid_capacity_kwh'")

        observation = self.env_config.get("observation") or "paper"

        if self.is_market and observation not in OBSERVATION_NAMES:
            raise SpecError(
                f"unknown observation {observation!r}; "
                f"choose from {list(OBSERVATION_NAMES)}"
            )

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
        """The scenario file that ``scenario`` names (when it is a file name)."""
        return (REPO / self.scenario).resolve()

    def folder(self, exp_dir: Optional[Path] = None) -> Path:
        """The experiment's folder: ``exp_dir``, default ``<runs root>/<name>``."""
        return Path(exp_dir) if exp_dir else runs_root() / self.name

    def scenario_file(
        self, exp_dir: Optional[Path] = None, variant: Optional[str] = None
    ) -> Path:
        """The scenario file the runs of ``variant`` read: the arm's or
        ``SCENARIO_FILE`` in the experiment's folder when ``scenario`` is the scenario
        itself, else the file it names."""
        if isinstance(self.arm(variant).scenario, dict):
            name = f"scenario_{variant}.json" if variant else SCENARIO_FILE
            return self.folder(exp_dir) / name

        return self.arm(variant).scenario_path

    def arm(self, variant: Optional[str]) -> "Experiment":
        """The arm of ``variant`` as a complete experiment: this one with what the
        variant gives overwritten (see the module); itself for ``None``."""
        if variant is None:
            return self

        changes = self.variants[variant]
        given = changes.get("scenario")
        base = self.inline_scenario() if isinstance(given, dict) else self
        data = overwrite(base.to_dict(), changes)
        data |= {"variants": {}, "test": {}}

        if "test_periods" in changes:
            data["test_days"] = []

        return Experiment.from_dict(data, self.name, check_files=False)

    @property
    def run_resources(self) -> dict:
        """What one run asks of a SLURM cluster: ``cpus``, ``mem_gb``, ``minutes``
        and ``node``, the spec's ``resources`` over the defaults."""
        return RESOURCE_DEFAULTS | self.resources

    def heldout_episodes(self) -> list[tuple[int, str]]:
        """The held-out evaluation's episodes: every test day once, in order, each
        with its seed (2000, 2001, ...)."""
        return [(HELDOUT_SEED_START + i, day) for i, day in enumerate(self.test_days)]

    def heldout_options(self) -> list[dict]:
        """The ``reset`` options of ``heldout_episodes``: the day, its period's name
        and whether it carries on from the day before."""
        return [
            {"day": day, "period": name, "carry": index > 0}
            for name, days in self.test_periods.items()
            for index, day in enumerate(days)
        ]

    def traced_days(self) -> list[str]:
        """The test days kept step by step (none unless ``results_detail`` is
        ``"detailed"``)."""
        if self.results_detail != "detailed":
            return []

        if isinstance(self.trace_days, list):
            return [d for d in self.test_days if d in self.trace_days]

        return self.test_days[: self.trace_days]

    def heldout_config(
        self, exp_dir: Optional[Path] = None, variant: Optional[str] = None
    ) -> dict:
        """The environment config of the held-out evaluation (test days) of a run of
        ``variant``; ``exp_dir`` as in ``expand``."""
        arm = self.arm(variant)
        config: dict = {"days": arm.test_days}

        if arm.scenario:
            config["scenario"] = str(self.scenario_file(exp_dir, variant))

        return config | arm.env_config

    # --- Writing and profiles ---------------------------------------------------------
    def to_dict(self) -> dict:
        """The experiment as a JSON-serialisable dict that ``from_dict`` loads back to
        an equal ``Experiment``; days are written out as lists of ISO dates."""
        return asdict(self)

    def inline_scenario(self) -> "Experiment":
        """This experiment with every scenario file read in: its own into ``scenario``
        and a variant's into that variant, so that it holds every input of its runs
        (itself if there is no file name to read)."""
        named = {
            name: changes
            for name, changes in self.variants.items()
            if isinstance(changes.get("scenario"), str)
        }

        prices = isinstance(self.scenario, dict) and isinstance(
            self.scenario.get("dso", {}).get("prices"), str
        )

        if not isinstance(self.scenario, str) and not named and not prices:
            return self

        out = copy.deepcopy(self)

        if isinstance(self.scenario, str):
            out.scenario = _read_scenario(self.scenario_path)
        elif prices:
            _read_prices(out.scenario, "scenario")

        for name, changes in named.items():
            path = (REPO / changes["scenario"]).resolve()
            out.variants[name]["scenario"] = _read_scenario(path)

        return out

    def dated(self, when: datetime) -> "Experiment":
        """This experiment named ``<name>-<YYYYMMDD>-<HHMMSS>`` at ``when``: a new
        name for another start of the same experiment file."""
        return replace(copy.deepcopy(self), name=f"{self.name}-{when:%Y%m%d-%H%M%S}")

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
        learning to happen, from the settings each arm really uses.

        For each arm (or the experiment alone, without variants) the budget is one
        training batch (``train_batch_size_per_learner``, else
        ``TEST_DEFAULT_BUDGET``). The largest over the arms wins.
        """
        budgets = []

        for variant in list(self.variants) or [None]:
            settings = self.arm(variant).training.get(algorithm, {})
            budgets.append(
                settings.get("train_batch_size_per_learner") or TEST_DEFAULT_BUDGET
            )

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
        periods = _first_days(self.test_periods, test.get("test_days", 1))
        test_days = [day for days in periods.values() for day in days]
        trace_days = self.trace_days

        if isinstance(trace_days, list):  # those the test version still has
            trace_days = [d for d in trace_days if d in test_days] or 1

        description = f"Test version of {self.name}"

        if self.description:
            description += f": {self.description}"

        version = replace(
            copy.deepcopy(self),
            name=f"{self.name}--test",
            seeds=list(test.get("seeds", self.seeds[:1])),
            train_days=self.train_days[: test.get("train_days", 1)],
            test_days=test_days,
            test_periods=periods,
            variants={
                name: {
                    k: v for k, v in changes.items() if k not in NOT_IN_A_TEST_VARIANT
                }
                for name, changes in self.variants.items()
            },
            budget=budget,
            eval_points=None,
            eval_episodes=test.get("eval_episodes", 1),
            trace_days=trace_days,
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
        exp_dir = self.folder(exp_dir)
        variants = self.variants or {None: {}}
        specs: list[RunSpec] = []

        for algorithm in self.algorithms:
            for paradigm in self.paradigms:
                for variant in variants:
                    arm = self.arm(variant)
                    budget, every = arm._budgets(algorithm)

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
                                env=arm.env,
                                env_config=self._env_config(seed, exp_dir, variant),
                                budget=budget,
                                eval_every=every,
                                eval_episodes=arm.eval_episodes,
                                training=dict(arm.training.get(algorithm, {})),
                                model=dict(arm.model),
                                out_dir=exp_dir / name,
                                index=len(specs),
                                num_env_runners=arm.num_env_runners,
                            )
                        )

        return specs

    def _budgets(self, algorithm: str) -> tuple[int, int]:
        """The budget of ``algorithm`` and the steps between its evaluations."""
        budget = self._per_algorithm(self.budget, algorithm, "budget")
        points = self._per_algorithm(self.eval_points, algorithm, "eval_points", True)

        return budget, budget // points if points else 0

    def _env_config(self, seed: int, exp_dir: Path, variant: Optional[str]) -> dict:
        arm = self.arm(variant)
        config: dict = {}

        if arm.scenario:
            config["scenario"] = str(self.scenario_file(exp_dir, variant))

        if arm.train_days:
            config["days"] = list(arm.train_days)

        config["seed"] = seed

        return config | arm.env_config


def _read_scenario(path: Path) -> dict:
    """The scenario at ``path`` with its price file read in."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SpecError(
            f"scenario file not found: {path} "
            "('scenario' is relative to the repository root)"
        ) from None
    except json.JSONDecodeError as error:
        raise SpecError(f"{path}: not valid JSON ({error})") from None

    if not isinstance(data, dict):
        raise SpecError(f"{path}: a scenario file holds one JSON object")

    _read_prices(data, path)

    return data


def _read_prices(data: dict, where: Any) -> None:
    """Read a scenario's price file, if it names one, into its ``dso.prices``."""
    dso = data.get("dso", {})

    if isinstance(dso.get("prices"), str):
        try:
            step = data.get("grid", {}).get("step_hours", GridSetup.step_hours)
            dso["prices"] = load_prices(dso["prices"], step)
        except (OSError, ValueError, KeyError) as error:
            raise SpecError(f"{where}: prices cannot be read ({error})") from None


def overwrite(base: dict, changes: dict) -> dict:
    """``base`` with the values of ``changes``: inside a section only those it names,
    any other value (a list too) as a whole."""
    out = dict(base)

    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = overwrite(out[key], value)
        else:
            out[key] = value

    return out


def resolve(spec: str | Path | Experiment, profile: str = "full") -> Experiment:
    """The experiment as it is started: ``spec`` (an experiment file or an
    ``Experiment``) with its scenario read in (``Experiment.inline_scenario``), in
    ``profile`` (``Experiment.with_profile``)."""
    experiment = spec if isinstance(spec, Experiment) else Experiment.load(spec)
    return experiment.inline_scenario().with_profile(profile)


# --------------------------------------------------------------------------------------
# Written out: every setting of an experiment with the value it runs with
# --------------------------------------------------------------------------------------
def written_out(data: dict, default_name: str = "experiment") -> dict:
    """An experiment file's JSON with every setting written out: what ``data``
    gives, as it gives it, and every other setting at its default, so a reader sees
    all that can be set. The runs it makes are those of ``data``.

    Besides the experiment's own fields (``Experiment``) that is ``training`` per
    algorithm with the RL layer's defaults (``core.rl_defaults.SETTINGS``) under the
    overrides, ``model`` with the network settings (``NETWORK``), ``resources``
    with ``RESOURCE_DEFAULTS`` and, for the market, ``env_config`` with
    ``MARKET_ENV_CONFIG``. Days, the scenario, the budget and the ``test`` block
    stay as written. Other RLlib ``training`` keys may still be added; they have
    RLlib's defaults until they are.

    ``SpecError`` if ``data`` is not an experiment (``Experiment.from_dict``, without
    looking for the scenario file). Writing out twice changes nothing.
    """
    from core.rl_defaults import NETWORK, SETTINGS

    experiment = Experiment.from_dict(data, default_name, check_files=False)
    e = experiment
    training = {a: SETTINGS[a] | e.training.get(a, {}) for a in e.algorithms}
    training |= {a: v for a, v in e.training.items() if a not in training}
    filled = {
        "name": data.get("name"),
        "description": e.description,
        "env": e.env,
        "scenario": e.scenario,
        "train_days": data.get("train_days", []),
        "test_periods": data.get("test_periods", {}),
        "env_config": (MARKET_ENV_CONFIG if e.is_market else {}) | e.env_config,
        "algorithms": e.algorithms,
        "paradigms": e.paradigms,
        "seeds": e.seeds,
        "variants": e.variants,
        "budget": e.budget,
        "eval_points": e.eval_points,
        "eval_episodes": e.eval_episodes,
        "results_detail": e.results_detail,
        "trace_days": e.trace_days,
        "training": training,
        "model": NETWORK | e.model,
        "max_parallel": e.max_parallel,
        "torch_threads": e.torch_threads,
        "num_env_runners": e.num_env_runners,
        "ray_thread_caps": e.ray_thread_caps,
        "resources": e.run_resources,
        "test": e.test,
    }

    if filled["name"] is None:  # the file's name, as ``load`` gives it
        del filled["name"]

    return copy.deepcopy(filled)


def to_text(data: dict) -> str:
    """An experiment as the JSON text of a file: two spaces per level, and a list or
    object of plain values on one line when it fits in ``_INLINE`` characters."""
    return _json(data, 0)


_INLINE = 72


def _json(value, level: int) -> str:
    one_line = json.dumps(value)
    plain = isinstance(value, (list, dict)) and not any(
        isinstance(v, (list, dict))
        for v in (value.values() if isinstance(value, dict) else value)
    )

    if not isinstance(value, (list, dict)) or (plain and len(one_line) <= _INLINE):
        return one_line

    inner = "  " * (level + 1)

    if isinstance(value, dict):
        items = [f"{json.dumps(k)}: {_json(v, level + 1)}" for k, v in value.items()]
        opening, closing = "{", "}"
    else:
        items = [_json(v, level + 1) for v in value]
        opening, closing = "[", "]"

    lines = ",\n".join(inner + item for item in items)

    return f"{opening}\n{lines}\n{'  ' * level}{closing}"


# --------------------------------------------------------------------------------------
# Resources
# --------------------------------------------------------------------------------------
def _check_resources(value, where: str) -> None:
    """``value`` maps some of ``cpus``, ``mem_gb`` and ``minutes`` to positive numbers
    (``cpus`` and ``minutes`` whole), and ``node`` to one node's name or None."""
    if not isinstance(value, dict):
        raise SpecError(f"'{where}' maps {sorted(RESOURCE_DEFAULTS)} to numbers")

    unknown = sorted(set(value) - set(RESOURCE_DEFAULTS))

    if unknown:
        raise SpecError(
            f"unknown '{where}' key(s) {unknown}; use {sorted(RESOURCE_DEFAULTS)}"
        )

    node = value.get("node")

    if node is not None and (
        not isinstance(node, str) or not node or any(c in node for c in " ,[]")
    ):
        raise SpecError(
            f"'{where}.node' is one node's name (e.g. 'blackwell1') or null"
        )

    for key, number in value.items():
        if key == "node":
            continue
        kinds = (int, float) if key == "mem_gb" else int
        if isinstance(number, bool) or not isinstance(number, kinds) or number <= 0:
            raise SpecError(
                f"'{where}.{key}' must be a positive "
                f"{'number' if key == 'mem_gb' else 'integer'}"
            )


# --------------------------------------------------------------------------------------
# Days
# --------------------------------------------------------------------------------------
def _first_days(periods: dict, count: int) -> dict[str, list[str]]:
    """The first ``count`` days of ``periods``, in their periods."""
    out = {}

    for name, days in periods.items():
        if count > 0:
            out[name] = days[:count]
            count -= len(out[name])

    return out


def _periods(data: dict) -> dict[str, list[str]]:
    """The experiment's ``test_periods``, each with its days written out."""
    periods = data.get("test_periods") or {}

    if not isinstance(periods, dict):
        raise SpecError("'test_periods' must map a name to its days")

    return {name: _days(days, "test_periods") for name, days in periods.items()}


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
