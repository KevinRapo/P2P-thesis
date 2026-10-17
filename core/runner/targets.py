"""Where an experiment runs: a target.

``hpc/targets.toml`` names the targets. ``local`` is this machine (a detached worker,
``launch.py``). A target of kind ``slurm`` is a SLURM cluster (``slurm.py``): on the
cluster itself, where ``sbatch`` exists, it submits directly (``SlurmTarget``); from
another machine, such as the PC, the same target is driven over SSH (``RemoteTarget``,
``remote.py``): it runs the runner's CLI on the cluster and copies the results back.

A ``Target`` is what the CLI and the Studio talk to, so neither needs to know how
or where the runs happen:

    check(spec)                whether the target is ready, as one report (see below)
    start(spec, profile)       check, then queue an experiment; returns its name
    overview(experiment)       the experiments there, each with its summary and runs
    runs(experiment)           the runs of one experiment
    stop(experiment, run)      stop an experiment or one run
    sync(experiment)           make the results available here; returns their folder
    close()                    let go of what the target holds (a connection)

``check`` is the one source of readiness. Its report::

    {"target": name, "ok": bool, "problems": [str, ...],
     "local_commit": this checkout's commit, "cluster_commit": the cluster's,
     "active": [experiments with queued or running runs]}

``ok`` is true when there are no problems; keys that do not apply are None. ``start``
refuses with the problems of the report, so what is shown before a start and what stops
it are the same list.

``local`` and a ``slurm`` target on the cluster read ``runs/`` directly
(``DirectTarget``); they differ in how runs are started and stopped, and in asking
SLURM for the state of the tasks. A ``RemoteTarget`` reads the cluster through its
CLI, and its results from the copy that ``sync`` keeps here (the target's ``mirror``).
"""

from __future__ import annotations

import dataclasses
import importlib.metadata
import shutil
import subprocess
import tomllib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from core import settings as machine
from core.runner import launch, registry
from core.runner.registry import RunState
from core.runner.spec import REPO, Experiment, SpecError, runs_root

if TYPE_CHECKING:  # remote.py loads asyncssh: imported only where a Remote is built
    from core.runner.remote import Remote

TARGETS_FILE = REPO / "hpc" / "targets.toml"
_SHIP = 'commit, then run `git shipc "message"` (it pushes and updates the cluster)'


class TargetError(RuntimeError):
    """The target is unknown, not ready, or its settings are wrong; the message says
    what to do."""


def _report(target: str, problems: list[str], **fields: Any) -> dict:
    """The report of ``Target.check`` (see the module)."""
    found = {
        "target": target,
        "ok": not problems,
        "problems": problems,
        "local_commit": None,
        "cluster_commit": None,
        "active": None,
    }
    return found | fields


# --------------------------------------------------------------------------------------
# What a target offers
# --------------------------------------------------------------------------------------
class Target(ABC):
    """Where experiments run and where their results are read from."""

    name: str
    copied: Optional[int] = None  # files the last ``sync`` copied (None: no copying)

    @abstractmethod
    def check(
        self, spec_path: str | Path | None = None, allow_uncommitted: bool = False
    ) -> dict:
        """Whether the target is ready, as the report in the module. With ``spec_path``
        it also covers that experiment. ``allow_uncommitted`` leaves out the problems
        about code that is not committed or not the cluster's (development only)."""

    def start(
        self,
        spec_path: str | Path,
        profile: str = "full",
        allow_uncommitted: bool = False,
    ) -> str:
        """Queue the experiment in ``spec_path`` (``profile`` ``"full"`` or
        ``"test"``) and start it; returns the experiment's name.

        Refuses with ``TargetError`` listing the problems if ``check`` finds any.
        ``allow_uncommitted=True`` is for development only: the cluster then runs
        whatever its checkout holds, which may not be what is here.
        """
        report = self.check(spec_path, allow_uncommitted=allow_uncommitted)
        if not report["ok"]:
            problems = "; ".join(report["problems"])
            raise TargetError(f"cannot start on {self.name}: {problems}")
        return self._start(spec_path, profile)

    @abstractmethod
    def _start(self, spec_path: str | Path, profile: str) -> str:
        """Queue and start, once ``check`` has passed."""

    @abstractmethod
    def overview(self, experiment: Optional[str] = None) -> list[dict]:
        """The experiments there (or just ``experiment``), each ``{"name",
        "description", "summary" (``registry.summary``), "modified" (seconds since the
        epoch), "spec" (its ``experiment.json``, None if it has none), "runs" (its
        ``RunState`` list in the order of its grid)}``. An experiment that does not
        exist is an error."""

    def runs(self, experiment: str) -> list[RunState]:
        """The runs of one experiment, in the order of its grid."""
        (entry,) = self.overview(experiment)
        return entry["runs"]

    @abstractmethod
    def stop(self, experiment: str, run: Optional[str] = None) -> dict:
        """Stop a whole experiment or one run; returns what was stopped."""

    @abstractmethod
    def sync(self, experiment: str) -> Optional[Path]:
        """Make the experiment's files available on this machine; returns their
        folder (None if there are none)."""

    def close(self) -> None:
        """Let go of what the target holds open (nothing, for most)."""


# --------------------------------------------------------------------------------------
# Targets that read runs/ directly
# --------------------------------------------------------------------------------------
class DirectTarget(Target):
    """A target whose experiments are folders on this machine (``root``, default
    ``$MARLEM_RUNS`` or ``<repo>/runs``, looked up at each call)."""

    def __init__(self, name: str, root: Optional[Path] = None) -> None:
        self.name = name
        self._root = Path(root) if root else None

    @property
    def root(self) -> Path:
        return self._root or runs_root()

    def _slurm(self, experiment: str) -> Optional[dict]:
        """The SLURM state of the experiment's tasks (None: not a SLURM target)."""
        return None

    def overview(self, experiment: Optional[str] = None) -> list[dict]:
        if experiment is None:
            names = registry.experiments(self.root)
        elif (self.root / experiment).is_dir():
            names = [experiment]
        else:
            raise FileNotFoundError(f"no experiment '{experiment}' in {self.root}")
        return [self._entry(name) for name in names]

    def _entry(self, name: str) -> dict:
        slurm = self._slurm(name)  # one SLURM question for the summary and the runs
        spec = registry.read_json(self.root / name / "experiment.json")
        return {
            "name": name,
            "description": (spec or {}).get("description", ""),
            "summary": registry.summary(name, self.root, slurm),
            "modified": (self.root / name).stat().st_mtime,
            "spec": spec,
            "runs": registry.runs(name, self.root, slurm),
        }

    def sync(self, experiment: str) -> Optional[Path]:
        """The files are here already: nothing to copy."""
        folder = self.root / experiment
        return folder if folder.is_dir() else None


class LocalTarget(DirectTarget):
    """This machine: a detached worker runs the jobs (``launch.py``)."""

    def __init__(self, root: Optional[Path] = None) -> None:
        super().__init__("local", root)

    def check(
        self, spec_path: str | Path | None = None, allow_uncommitted: bool = False
    ) -> dict:
        return _report(self.name, [])

    def _start(self, spec_path: str | Path, profile: str) -> str:
        return launch.start(spec_path, self.root, profile).name

    def stop(self, experiment: str, run: Optional[str] = None) -> dict:
        return launch.stop(experiment, run, self.root)


class SlurmTarget(DirectTarget):
    """A SLURM cluster, used from the cluster (``sbatch`` available): one job array
    per experiment (``slurm.py``).

    Args:
        name: The target's name in ``targets.toml``.
        settings: Its table there; ``account`` and ``partitions`` are needed here.
        root: The folder with the experiments.
    """

    def __init__(
        self, name: str, settings: dict[str, Any], root: Optional[Path] = None
    ) -> None:
        super().__init__(name, root)
        self.settings = settings

    def _setting(self, key: str) -> Any:
        return _setting(self.name, self.settings, key)

    def _slurm(self, experiment: str) -> Optional[dict]:
        from core.runner import slurm

        return slurm.states(self.root / experiment)

    def check(
        self, spec_path: str | Path | None = None, allow_uncommitted: bool = False
    ) -> dict:
        """Whether jobs can be submitted from here. The commit is this checkout's:
        a queued task runs the checkout as it is when the task starts, so ``active``
        lists the experiments for which it must not be updated or edited."""
        problems = []
        if shutil.which("sbatch") is None:
            problems.append("sbatch not found: this is not a cluster's login node")
        try:
            importlib.metadata.version("submitit")
        except importlib.metadata.PackageNotFoundError:
            problems.append("submitit is not installed in this Python environment")
        commit = _git("rev-parse", "HEAD")
        busy = {"queued", "running"}
        active = [
            entry["name"]
            for entry in self.overview()
            if busy & set(entry["summary"]["counts"])
        ]
        return _report(
            self.name,
            problems,
            local_commit=commit,
            cluster_commit=commit,
            active=active,
        )

    def _start(self, spec_path: str | Path, profile: str) -> str:
        from core.runner import slurm

        exp_dir = slurm.start(
            spec_path,
            account=self._setting("account"),
            partitions=self._setting("partitions"),
            root=self.root,
            profile=profile,
        )
        return exp_dir.name

    def stop(self, experiment: str, run: Optional[str] = None) -> dict:
        from core.runner import slurm

        return slurm.stop(experiment, run, self.root)


def _setting(name: str, settings: dict[str, Any], key: str) -> Any:
    if key not in settings:
        raise TargetError(f"target '{name}' has no '{key}' in {TARGETS_FILE}")
    value = settings[key]
    if isinstance(value, _Unset):
        raise TargetError(
            f"target '{name}': '{key}' needs {value.key}; set it in .env "
            "(see .env.example) or as an environment variable"
        )
    return value


def _git(*args: str) -> Optional[str]:
    """The output of a git command in the repository (None if git says no)."""
    done = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True
    )
    return done.stdout.strip() if done.returncode == 0 else None


# --------------------------------------------------------------------------------------
# A cluster driven from this machine
# --------------------------------------------------------------------------------------
_RUN_FIELDS = {field.name for field in dataclasses.fields(RunState)}


def _run_state(data: dict) -> RunState:
    """A ``RunState`` from its JSON; keys it does not know are ignored (a cluster on a
    newer version of the code may send more)."""
    return RunState(**{key: value for key, value in data.items() if key in _RUN_FIELDS})


def _plain_name(name: str) -> str:
    """An experiment name that is one folder name (it becomes part of two paths)."""
    if not name or name.startswith(".") or any(c in name for c in "/\\:"):
        raise TargetError(f"{name!r} is not an experiment name")
    return name


def _repo_relative(spec_path: str | Path) -> Optional[str]:
    """The spec's path relative to the repository, with forward slashes (None if it
    is outside)."""
    path = Path(spec_path)
    if not path.is_absolute() and not path.is_file():
        path = REPO / path  # as the notebooks write it: relative to the root
    try:
        return path.resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError:
        return None


class RemoteTarget(Target):
    """A SLURM cluster used from another machine: every call runs the runner's CLI on
    the cluster's login node over SSH (``remote.py``) and reads its JSON, so the
    cluster does exactly what it does when used from there. Results are copied back
    by ``sync`` into ``mirror/<experiment>``; ``local_runs`` reads that copy.

    The cluster runs its own checkout of the repository, not the files here, so a
    start needs the spec and its scenario committed here, both machines at one commit
    and the cluster's checkout clean (``check`` lists what is not).

    Args:
        name: The target's name in ``targets.toml``.
        settings: Its table there; ``host``, ``repo``, ``python`` and ``mirror`` are
            needed here.
        remote: The connection (default: built from ``settings``, opened by the first
            call that needs it).
        mirror: The folder for the copied results (default: ``settings["mirror"]``
            in the repository).
    """

    def __init__(
        self,
        name: str,
        settings: dict[str, Any],
        remote: Optional["Remote"] = None,
        mirror: Optional[Path] = None,
    ) -> None:
        self.name = name
        self.settings = settings
        if mirror is None:
            mirror = REPO / _setting(name, settings, "mirror")
        self.mirror = Path(mirror)
        if remote is None:
            from core.runner.remote import Remote

            remote = Remote(
                _setting(name, settings, "host"),
                _setting(name, settings, "repo"),
                _setting(name, settings, "python"),
            )
        self.remote = remote

    def close(self) -> None:
        self.remote.close()

    # --- Ready? -----------------------------------------------------------------------
    def check(
        self, spec_path: str | Path | None = None, allow_uncommitted: bool = False
    ) -> dict:
        """Whether an experiment can start on the cluster: it answers and its own
        ``check`` passes, its checkout is at this machine's commit and has no changes
        and, with ``spec_path``, the spec and its scenario are committed here.

        Never raises for a connection problem: it is a problem of the report."""
        from core.runner.remote import RemoteError

        local = _git("rev-parse", "HEAD")
        found = _report(self.name, [], local_commit=local)
        problems: list[str] = []  # always block a start
        unshipped: list[str] = []  # about code the cluster does not have
        try:
            cluster = self.remote.runner("check", "--target", self.name, accept=(0, 1))
            commit = self.remote.head()
            dirty = self.remote.uncommitted()
        except RemoteError as error:
            problems.append(str(error))
        else:
            problems += [f"on the cluster: {text}" for text in cluster["problems"]]
            found |= {"cluster_commit": commit, "active": cluster["active"]}
            if local is None:
                unshipped.append(
                    "cannot read this machine's commit (is it a git repository?)"
                )
            elif local != commit:
                unshipped.append(
                    f"the cluster is at commit {commit[:8]} but this machine at "
                    f"{local[:8]}: {_SHIP}"
                )
            if dirty:
                unshipped.append(
                    "the cluster's checkout has uncommitted changes: clean it there"
                )
        if spec_path is not None:
            spec_problems, spec_unshipped = self._check_spec(spec_path)
            problems += spec_problems
            unshipped += spec_unshipped
        problems += [] if allow_uncommitted else unshipped
        return found | {"problems": problems, "ok": not problems}

    @staticmethod
    def _check_spec(spec_path: str | Path) -> tuple[list[str], list[str]]:
        """The problems of the spec and its scenario as files of the repository:
        ``(always, unshipped)``."""
        relative = _repo_relative(spec_path)
        if relative is None:
            return [
                f"{spec_path} is not inside the repository {REPO}: the cluster runs "
                "its own checkout, so the spec must be a file of it"
            ], []
        try:
            scenario = Experiment.load(REPO / relative, check_files=False).scenario
        except SpecError as error:
            return [f"{relative}: {error}"], []
        unshipped = []
        for path in [relative, *([Path(scenario).as_posix()] if scenario else [])]:
            if _git("ls-files", "--error-unmatch", "--", path) is None:
                unshipped.append(f"{path} is not tracked by git: {_SHIP}")
            elif _git("status", "--porcelain", "--", path):
                unshipped.append(f"{path} has uncommitted changes here: {_SHIP}")
        return [], unshipped

    # --- Start and stop ---------------------------------------------------------------
    def _start(self, spec_path: str | Path, profile: str) -> str:
        relative = _repo_relative(spec_path)  # inside the repository: check said so
        answer = self.remote.runner(
            "start", relative, "--target", self.name, "--profile", profile
        )
        return answer["experiment"]

    def stop(self, experiment: str, run: Optional[str] = None) -> dict:
        args = ["stop", experiment, *([run] if run else []), "--target", self.name]
        answer = self.remote.runner(*args)
        return {k: v for k, v in answer.items() if k not in ("target", "experiment")}

    # --- Reading ----------------------------------------------------------------------
    def overview(self, experiment: Optional[str] = None) -> list[dict]:
        """One call to the cluster; the entries are ``status``'s, with the runs turned
        into ``RunState``."""
        args = ["status", *([experiment] if experiment else []), "--target", self.name]
        answer = self.remote.runner(*args)
        entries = [answer] if experiment else answer["experiments"]
        return [
            entry | {"runs": [_run_state(run) for run in entry["runs"]]}
            for entry in entries
        ]

    # --- Results ----------------------------------------------------------------------
    def sync(self, experiment: str) -> Path:
        """Replace ``mirror/<experiment>`` with a fresh copy of the experiment's files
        on the cluster (checkpoints and SLURM's own files stay there); returns that
        folder. ``copied`` is the number of files copied. If the copy fails the
        previous mirror stays."""
        _plain_name(experiment)
        folder = self.mirror / experiment
        self.copied = self.remote.pull(f"runs/{experiment}", folder)
        return folder

    def local_runs(self, experiment: str) -> list[RunState]:
        """The runs of the synced copy, read from files like a local experiment."""
        return registry.runs(experiment, self.mirror)


# --------------------------------------------------------------------------------------
# targets.toml
# --------------------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class _Unset:
    """A target setting whose ``${key}`` is not set on this machine; an error only
    when the target uses it."""

    key: str


def _expand(value: Any) -> Any:
    """``value`` with every ``${KEY}`` / ``${KEY:-default}`` in its strings replaced
    by this machine's setting (``core/settings.py``)."""
    if isinstance(value, str):
        return machine.expand(value, _Unset)
    if isinstance(value, list):
        return [_expand(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    return value


def settings(path: Optional[Path] = None) -> dict[str, dict]:
    """The targets in ``hpc/targets.toml`` (or ``path``) by name, with the
    ``${KEY}`` references to this machine's settings filled in; ``local`` is always
    there."""
    found: dict[str, dict] = {"local": {"kind": "local"}}
    path = Path(path) if path else TARGETS_FILE
    if path.is_file():
        try:
            found |= tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as error:
            raise TargetError(f"{path}: not valid TOML ({error})") from None
    return _expand(found)


def names(path: Optional[Path] = None) -> list[str]:
    """The names of the targets."""
    return list(settings(path))


def get(
    name: str = "local", root: Optional[Path] = None, path: Optional[Path] = None
) -> Target:
    """The target called ``name`` in ``targets.toml`` (``root``: the folder with its
    experiments, default the runs root, or for a cluster seen from another machine its
    ``mirror``; ``path``: another targets file). A ``slurm`` target is a
    ``SlurmTarget`` where ``sbatch`` exists, else a ``RemoteTarget``; nothing connects
    until it is used."""
    found = settings(path)
    if name not in found:
        raise TargetError(f"unknown target '{name}'; the targets are {list(found)}")
    kind = found[name].get("kind")
    if kind == "local":
        return LocalTarget(root)
    if kind == "slurm":
        if shutil.which("sbatch"):
            return SlurmTarget(name, found[name], root)
        return RemoteTarget(name, found[name], mirror=root)
    raise TargetError(
        f"target '{name}': 'kind' must be 'local' or 'slurm', not {kind!r}"
    )
