"""RunService: what the Runs page reads about training experiments, and what it starts.

A thin wrapper over ``core.runner``. An experiment runs on a **target** (``targets.py``,
named in ``hpc/targets.toml``): this PC, or a cluster driven over SSH. The service holds
one target object per name for the life of the Studio (a cluster's target keeps its SSH
connection open) and passes the calls on: ``overview``, ``check``, ``start``,
``start_new``, ``restart``, ``stop``, ``sync``. The start dialog edits an experiment
file's text; ``apply_preset`` rewrites the text as the test or the full experiment,
``quick_settings`` / ``apply_settings`` read and write the settings the dialog
offers as fields (paradigms, seeds, budget, PPO, workers, cluster resources), and
``describe`` turns it into the ``Experiment`` to start. The runner's records (the target's entries and report) are returned as they
are; every method is synchronous and may take seconds on a cluster, so the pages call
them through ``run.io_bound``.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

import json

from core.runner import targets
from core.runner.spec import (
    REPO,
    Experiment,
    SpecError,
    resolve,
    to_text,
    written_out,
)

# The settings a preset of the start dialog replaces: those the test version changes
# (``Experiment.test_version``); the test block itself stays, so it can be edited.
PRESET_KEYS = (
    "name",
    "description",
    "seeds",
    "train_days",
    "test_days",
    "budget",
    "eval_every",
    "eval_points",
    "eval_episodes",
    "trace_days",
    "resources",
)
PRESETS = ("test", "full")
# The settings the start dialog offers as fields, by their path in the JSON (V2:
# PPO's settings under training.ppo); the rest is edited in the JSON itself.
QUICK_SETTINGS: dict[str, tuple[str, ...]] = {
    "paradigms": ("paradigms",),
    "seeds": ("seeds",),
    "budget": ("budget",),
    "lr": ("training", "ppo", "lr"),
    "train_batch_size_per_learner": ("training", "ppo", "train_batch_size_per_learner"),
    "minibatch_size": ("training", "ppo", "minibatch_size"),
    "num_epochs": ("training", "ppo", "num_epochs"),
    "entropy_coeff": ("training", "ppo", "entropy_coeff"),
    "clip_param": ("training", "ppo", "clip_param"),
    "gamma": ("training", "ppo", "gamma"),
    "num_env_runners": ("num_env_runners",),
    "max_parallel": ("max_parallel",),
    "torch_threads": ("torch_threads",),
    "cpus": ("resources", "cpus"),
    "mem_gb": ("resources", "mem_gb"),
    "minutes": ("resources", "minutes"),
}


# --------------------------------------------------------------------------------------
# The service
# --------------------------------------------------------------------------------------
class RunService:
    """The experiments of the targets and their runs.

    Args:
        root: The folder with this PC's experiments; default ``$MARLEM_RUNS`` or
            ``<repo>/runs``.
        specs: The folder with the experiment specs; default ``<repo>/experiments``.
    """

    def __init__(
        self,
        root: Optional[Path] = None,
        specs: Optional[Path] = None,
    ) -> None:
        self._root = Path(root) if root else None
        self._specs = Path(specs) if specs else REPO / "experiments"
        self._targets: dict[str, targets.Target] = {}
        self._made = threading.Lock()  # a target is made once, from whichever thread
        self._syncing = threading.Lock()  # one copy at a time: ``copied`` is per target

    # --- Targets ---------------------------------------------------------------------
    def target_names(self) -> list[tuple[str, str]]:
        """``(name, label)`` of every target in ``targets.toml``: the label is its
        ``label`` there, else its name."""
        return [
            (name, cfg.get("label", name)) for name, cfg in targets.settings().items()
        ]

    def target(self, name: str) -> targets.Target:
        """The target called ``name``, made on first use and kept (nothing connects
        until a call needs it)."""
        with self._made:
            if name not in self._targets:
                # ``root`` is this PC's folder; a cluster keeps its own copy elsewhere.
                root = self._root if name == "local" else None
                self._targets[name] = targets.get(name, root=root)
            return self._targets[name]

    def close(self) -> None:
        """Close every target made (the SSH connections)."""
        with self._made:
            made, self._targets = list(self._targets.values()), {}
        for target in made:
            target.close()

    # --- On a target -----------------------------------------------------------------
    def overview(self, target: str) -> list[dict]:
        """Every experiment of the target with its summary, runs and spec (see
        ``Target.overview``), the most recently changed first."""
        entries = self.target(target).overview()
        return sorted(
            entries, key=lambda entry: entry.get("modified", 0.0), reverse=True
        )

    def check(self, target: str, spec: Optional[targets.Spec] = None) -> dict:
        """Whether the target is ready (with ``spec``, a file or an ``Experiment``: to
        start that experiment), as the report of ``Target.check``."""
        return self.target(target).check(spec)

    def fit_problems(
        self, target: str, spec: targets.Spec, nodes: Optional[dict]
    ) -> list[str]:
        """What the experiment asks that the target cannot give, on the ``nodes`` of
        its last check (``Target.fit_problems``): no connection, so it can run on
        every edit."""
        return self.target(target).fit_problems(spec, nodes)

    def start(self, target: str, spec: targets.Spec, profile: str = "full") -> str:
        """Queue and start the experiment ``spec`` (a file or an ``Experiment``;
        ``profile`` ``"full"`` or ``"test"``); returns its name. It checks first and
        raises ``TargetError`` with the problems if the target is not ready."""
        return self.target(target).start(spec, profile)

    def start_new(self, target: str, spec: targets.Spec, profile: str = "full") -> str:
        """Start ``spec`` as a new experiment (``Target.start_new``: a dated name if
        its name is taken there); returns the name it started under."""
        return self.target(target).start_new(spec, profile)

    def restart(self, target: str, experiment: str) -> str:
        """Start an experiment again from the inputs saved in its folder
        (``Target.restart``): its failed, stopped and lost runs train again."""
        return self.target(target).restart(experiment)

    def stop(self, target: str, experiment: str, run: Optional[str] = None) -> dict:
        """Stop a whole experiment, or one run of it (see ``Target.stop``). Kills
        processes or cancels SLURM tasks, so it can take a few seconds."""
        return self.target(target).stop(experiment, run)

    def sync(self, target: str, experiment: str) -> tuple[Optional[Path], int]:
        """Copy the experiment's results to this PC: ``(folder, files copied)``. On this
        PC the files are there already: 0 copied."""
        with self._syncing:
            found = self.target(target)
            folder = found.sync(experiment)
            return folder, found.copied or 0

    # --- Experiment specs ------------------------------------------------------------
    def spec_files(self) -> list[dict]:
        """The specs in the specs folder, by file name, with what the start dialog
        shows. Each: ``path``, ``name``, ``description``, ``runs``, ``budget``
        (environment steps per run, an int or one per algorithm), ``resources`` (cpus,
        mem_gb, minutes and node per run on a cluster), ``text`` (the file as it is
        written), ``experiment`` (the ``Experiment``) and ``error``: why the file does
        not load (the other fields but ``text`` are then None)."""
        found = []
        for path in sorted(self._specs.glob("*.json")):
            text = path.read_text(encoding="utf-8")
            record = self.describe(text, path.stem)
            if record["error"]:
                record["name"] = path.stem
            found.append({"path": path, "text": text} | record)
        return found

    def apply_preset(
        self, text: str, preset: str, template_text: str, default_name: str
    ) -> str:
        """The editor's text with a preset applied (``apply_preset``), written out
        (``editable``)."""
        return editable(apply_preset(text, preset, template_text, default_name))

    def quick_settings(self, text: str) -> dict:
        """The editor's values of ``QUICK_SETTINGS`` (``quick_settings``)."""
        return quick_settings(text)

    def apply_settings(self, text: str, values: dict) -> str:
        """The editor's text with quick settings changed (``apply_settings``)."""
        return apply_settings(text, values)

    def editable(self, text: str, default_name: str = "experiment") -> str:
        """A template's text as the start dialog edits it (``editable``)."""
        return editable(text, default_name)

    def describe(self, text: str, default_name: str = "experiment") -> dict:
        """An experiment file's text, as edited in the start dialog: the record of
        ``spec_files`` (without ``path`` and ``text``), with ``experiment``, the
        ``Experiment`` to start (None, and ``error`` says why, if the text is not an
        experiment or its scenario cannot be read, as a start would read it).
        ``default_name`` is the name when the text gives none."""
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            return _record(None, f"not valid JSON ({error})")
        try:
            experiment = Experiment.from_dict(data, default_name)
            resolve(experiment)  # reads the scenario, as the start will
        except (OSError, SpecError) as error:
            return _record(None, str(error))
        return _record(experiment)


def apply_preset(
    text: str, preset: str, template_text: str, default_name: str = "experiment"
) -> str:
    """An experiment text with a preset applied to the settings of ``PRESET_KEYS``:
    ``"full"`` gives them the template's values (one the template does not give is
    removed, so it has its default), ``"test"`` the values of the template's test
    version (``Experiment.test_version``, from the experiment with the template's
    values, so applying it twice changes nothing). Every other setting keeps its
    edit and its place. ``default_name`` is the name when the template gives none.
    ``ValueError`` says why the text or the template is not an experiment."""
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r}; choose from {list(PRESETS)}")
    data, template = _json_object(text), _json_object(template_text)
    values = {key: template.get(key) for key in PRESET_KEYS}
    if preset == "test":
        full = _replaced(data, values)
        test = Experiment.from_dict(full, default_name, check_files=False)
        test_data = test.test_version().to_dict()
        values = {key: test_data[key] for key in PRESET_KEYS}
    return to_text(_replaced(data, values))


def quick_settings(text: str) -> dict:
    """The values of ``QUICK_SETTINGS`` in an experiment text (a setting it does
    not give is None; a budget per algorithm gives PPO's). ``{}`` if the text is
    not a JSON object."""
    try:
        data = _json_object(text)
    except (ValueError, SpecError):
        return {}
    found = {}
    for name, path in QUICK_SETTINGS.items():
        value: object = data
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        if name == "budget" and isinstance(value, dict):
            value = value.get("ppo")
        found[name] = value
    return found


def apply_settings(text: str, values: dict) -> str:
    """An experiment text with the given ``QUICK_SETTINGS`` set (a value of None
    removes the setting, so it has its default); every other setting keeps its
    edit and its place. A budget given per algorithm stays a dict (PPO's entry is
    set). ``ValueError`` if the text is not a JSON object or a name is unknown."""
    data = _json_object(text)
    for name, value in values.items():
        if name not in QUICK_SETTINGS:
            raise ValueError(f"unknown quick setting {name!r}")
        *parents, last = QUICK_SETTINGS[name]
        node = data
        for key in parents:
            if not isinstance(node.get(key), dict):
                node[key] = {}
            node = node[key]
        if name == "budget" and isinstance(node.get(last), dict):
            node, last = node[last], "ppo"
        if value is None:
            node.pop(last, None)
        else:
            node[last] = value
    return to_text(data)


def editable(text: str, default_name: str = "experiment") -> str:
    """An experiment text with every setting written out, each at its default where
    the text gives none (``core.runner.spec.written_out``), so the editor shows all
    that can be set. Text that is not an experiment is returned as it is, for
    ``describe`` to say what is wrong. ``default_name`` as in ``describe``."""
    try:
        return to_text(written_out(_json_object(text), default_name))
    except (ValueError, SpecError):
        return text


def _json_object(text: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"not valid JSON ({error})") from None
    if not isinstance(data, dict):
        raise SpecError("an experiment file holds one JSON object")
    return data


def _replaced(data: dict, values: dict) -> dict:
    """``data`` with the settings of ``values`` replaced in place, added at the end if
    new, and removed where the value is None (the default)."""
    found = {key: values.get(key, value) for key, value in data.items()}
    found |= {key: value for key, value in values.items() if key not in data}
    return {key: value for key, value in found.items() if value is not None}


def _record(experiment: Optional[Experiment], error: Optional[str] = None) -> dict:
    """What the start dialog shows of an experiment (see ``spec_files``)."""
    if experiment is None:
        keys = ("name", "description", "runs", "budget", "resources", "experiment")
        return dict.fromkeys(keys) | {"error": error}
    return {
        "name": experiment.name,
        "description": experiment.description,
        "runs": len(experiment.expand()),
        "budget": experiment.budget,
        "resources": experiment.run_resources,
        "experiment": experiment,
        "error": None,
    }
