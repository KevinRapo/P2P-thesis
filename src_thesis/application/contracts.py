"""Service interfaces used by the Studio, the CLI and notebooks.

Each protocol mirrors a method table in docs_thesis/thesis/architecture/04-application-layer.md.
Implementations live elsewhere: `application.demo` (sample data, no MARLEM)
and the real services (`config_files`, `grid_catalog`, later the ones backed by
the experiment layer). `container.build_services` decides which one a caller gets.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from src_thesis.application.models import (
    DryRunResult,
    ElementInfo,
    ExperimentFile,
    FieldChange,
    FileSummary,
    Finding,
    MatrixTable,
    NetworkInfo,
    NetworkSource,
    NetworkSummary,
    PowerFlowPreview,
    ProfileType,
    RepositoryHealth,
    RunCell,
    RunEstimate,
    RunResult,
    RunStatus,
    RunSummary,
    Series,
    TopologyView,
    ValidationReport,
)


class ConfigService(Protocol):
    """Experiment files: presets, the user's library, editing, comparing, sharing.

    Nothing here runs a simulation. Real implementation: ``FileConfigService``.
    """

    def list(self, kind: str | None = None) -> list[FileSummary]:
        """Presets and library files, for the Home and Library pages.

        Args:
            kind: ``"preset"`` or ``"draft"`` to list only one kind; ``None`` for all.
        """
        ...

    def load(self, file_id: str) -> ExperimentFile:
        """Read a library file or preset by ID.

        Raises:
            FileNotFoundError: Neither a library file nor a preset has this ID.
        """
        ...

    def new_from_preset(self, preset_id: str) -> ExperimentFile:
        """Copy a preset into the library as a new draft and return it.

        The draft gets a free ID (``<preset>-draft``, ``-draft-2``, …) and records
        the preset in ``meta.derived_from``.
        """
        ...

    def save(self, file: ExperimentFile, path: Path | None = None) -> str:
        """Write the file (to the library unless ``path`` is given).

        Returns:
            The path written.

        Raises:
            ValueError: The ID is a preset's or is not usable as a file name.
        """
        ...

    def clone(self, file_id: str, new_id: str) -> ExperimentFile:
        """Save a copy of ``file_id`` under ``new_id``, recording where it came from.

        Raises:
            FileExistsError: A file with ``new_id`` already exists.
        """
        ...

    def delete(self, file_id: str) -> None:
        """Delete a library file. Presets cannot be deleted."""
        ...

    def update(self, file: ExperimentFile, changes: dict[str, Any]) -> ExperimentFile:
        """A validated copy of ``file`` with each dotted path set; nothing is saved.

        Args:
            file: The file to change; it is not modified.
            changes: Dotted path → new value, e.g. ``{"market.mechanism": "seller"}``.

        Raises:
            ValueError: The result is not a valid experiment file.
        """
        ...

    def origin(self, file: ExperimentFile) -> ExperimentFile | None:
        """The preset or file named in ``meta.derived_from``; ``None`` if gone."""
        ...

    def resolve(self, file: ExperimentFile) -> ExperimentFile:
        """The file with every unset field filled from the defaults (02 §3)."""
        ...

    def expand(self, file: ExperimentFile) -> list[RunCell]:
        """The runs the file asks for.

        Sweep points × paradigms × algorithms × seeds, plus the baselines.
        """
        ...

    def hash(self, file: ExperimentFile) -> str:
        """Canonical sha256: equal for files that describe the same study (02 §6)."""
        ...

    def diff(self, a: ExperimentFile, b: ExperimentFile) -> list[FieldChange]:
        """Every field that differs between ``a`` and ``b``, as dotted paths."""
        ...

    def export_bundle(self, file: ExperimentFile) -> str:
        """Zip the file with the data files it references.

        Returns:
            The path of the zip.
        """
        ...

    def to_json(self, file: ExperimentFile) -> str:
        """The file as the pretty JSON that is saved and shared."""
        ...


class GridCatalogService(Protocol):
    """Networks before any experiment: what exists, what it looks like, one power flow.

    Real implementation: ``PandapowerGridCatalogService`` (SimBench and pandapower).
    """

    def list_networks(
        self, source_type: str | None = None, level: str | None = None
    ) -> list[NetworkInfo]:
        """The networks that can be chosen.

        Args:
            source_type: ``"simbench"``, ``"pandapower_builtin"`` or
                ``"pandapower_file"``; ``None`` for all.
            level: Voltage level filter, e.g. ``"LV"``.
        """
        ...

    def summary(self, source: NetworkSource) -> NetworkSummary:
        """Element counts, total load and generation of one network."""
        ...

    def topology(self, source: NetworkSource) -> TopologyView:
        """Buses with coordinates and branches, as plain data for plotting."""
        ...

    def elements(
        self, source: NetworkSource, bus: str | None = None
    ) -> list[ElementInfo]:
        """Loads, generators and storage, optionally only those on ``bus``."""
        ...

    def preview_powerflow(
        self, source: NetworkSource, day: str, step: int
    ) -> PowerFlowPreview:
        """One AC power flow of the unmodified network at one hour.

        Args:
            source: The network.
            day: Date (``YYYY-MM-DD``) of the profile values to use.
            step: Hour of that day (0–23).
        """
        ...


class ProfileService(Protocol):
    """Generation and demand profiles and how participants map onto a network (R3)."""

    def profile_types(self, source: NetworkSource | None = None) -> list[ProfileType]:
        """Profile types that can be assigned (SimBench catalogue)."""
        ...

    def preview(self, file: ExperimentFile, participant_id: str) -> Series:
        """Generation, demand and net profile of one participant over time."""
        ...

    def suggest_mapping(self, source: NetworkSource, rule: dict) -> list[dict]:
        """Participants placed on a network by a rule, e.g. "8 households with PV".

        Args:
            source: The network to place participants on.
            rule: The placement rule, e.g. ``{"type": "household_with_pv", "n": 8}``.

        Returns:
            Participant entries for the experiment file's ``participants`` list.
        """
        ...

    def days(self, file: ExperimentFile) -> dict[str, list[str]]:
        """The training and evaluation dates the file's ``time`` section selects."""
        ...

    def tariffs(self, file: ExperimentFile) -> Series:
        """Feed-in tariff and utility price over the time window."""
        ...


class ValidationService(Protocol):
    """Preflight checks before any run (02 §9)."""

    def validate(self, file: ExperimentFile, level: str = "full") -> ValidationReport:
        """Check a file and report findings with the field they concern.

        Args:
            file: The file to check.
            level: ``"schema"`` (instant), ``"references"`` (buses, files exist) or
                ``"full"`` (everything, including the dry run).
        """
        ...

    def dry_run(self, file: ExperimentFile) -> DryRunResult:
        """Build the environment and take one step, to catch errors early."""
        ...


class ExperimentService(Protocol):
    """Creating, starting, watching and cancelling runs (the experiment layer, 03)."""

    def create_runs(self, file: ExperimentFile) -> list[str]:
        """Validate, expand and write one run folder per run, in state READY.

        Returns:
            The new run IDs.
        """
        ...

    def start(self, run_ids: list[str]) -> None:
        """Queue runs; the worker pool starts them as slots become free."""
        ...

    def cancel(self, run_id: str) -> None:
        """Ask a run to stop; a queued run is cancelled at once."""
        ...

    def snapshot(self, run_id: str) -> RunStatus:
        """Current state, progress, last metrics and log tail of one run."""
        ...

    def list_runs(self, experiment_id: str | None = None) -> list[RunSummary]:
        """All runs, or only those of one experiment."""
        ...

    def estimate(self, file: ExperimentFile) -> RunEstimate:
        """How many runs the file creates and roughly how long they take."""
        ...

    def health(self) -> RepositoryHealth:
        """Repository and environment state shown on the Home page."""
        ...


class ResultService(Protocol):
    """Reading finished runs: outcomes, learning curves, replays, comparisons."""

    def summary(self, run_id: str) -> RunResult:
        """Research outcomes, RL return and manifest of one run."""
        ...

    def training_curve(self, run_id: str) -> Series:
        """Training and evaluation return per iteration."""
        ...

    def step_records(self, run_id: str, episode: int = 0) -> list[dict]:
        """Orders, trades, settlement and grid assessment per step of one episode."""
        ...

    def grid_series(self, run_id: str, episode: int = 0) -> Series:
        """Voltages, loadings, losses and violations over one episode."""
        ...

    def agent_series(self, run_id: str, episode: int = 0) -> Series:
        """Per-agent state of charge, net injection and profit over one episode."""
        ...

    def matrix(self, experiment_id: str, metric: str) -> MatrixTable:
        """Paradigm × algorithm table of ``metric`` (mean ± std over seeds)."""
        ...

    def compare(self, run_ids: list[str], metric: str) -> Series:
        """One metric of several runs, for overlaying."""
        ...

    def export(self, run_ids: list[str], fmt: str = "csv") -> str:
        """Write the runs' raw series to a file.

        Args:
            run_ids: Runs to export.
            fmt: ``"csv"`` or ``"json"``.

        Returns:
            The path written.
        """
        ...


__all__ = [
    "ConfigService",
    "GridCatalogService",
    "ProfileService",
    "ValidationService",
    "ExperimentService",
    "ResultService",
    "Finding",
]
