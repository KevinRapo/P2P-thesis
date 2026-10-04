"""ValidationService: preflight checks before any run (04 §5, 02 §9).

Final implementation: ``PreflightValidationService``, not built yet (R6-R7). Demo:
``DemoValidationService`` (fixed sample findings; nothing is checked).
"""

from __future__ import annotations

from typing import Protocol
from src_thesis.application.config_service import DemoConfigService
from src_thesis.application.models import (
    DryRunResult,
    ExperimentFile,
    Finding,
    Severity,
    ValidationReport,
)


# ---------------------------------------------------------------------- protocol
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


# ---------------------------------------------------------------------- final implementation (skeleton)
_NOT_BUILT = (
    "Not built yet: the final implementation of this service waits for its "
    "roadmap phase; the Studio uses the demo implementation until then."
)


class PreflightValidationService:
    """The final ``ValidationService``: the preflight checks of 02 §9 (R6-R7).

    Not implemented yet; every method raises.
    """

    def validate(self, file: ExperimentFile, level: str = "full") -> ValidationReport:
        """Will check schema (Pydantic), references, time, units, grid mapping, RL
        settings, protocol and resources, each finding with its field path."""
        raise NotImplementedError(_NOT_BUILT)

    def dry_run(self, file: ExperimentFile) -> DryRunResult:
        """Will build one environment with ``experiments.factory.environment.build_env``
        and take one step with the no-order policy."""
        raise NotImplementedError(_NOT_BUILT)


# ---------------------------------------------------------------------- demo implementation
class DemoValidationService:
    """Demo ``ValidationService``: fixed sample findings; nothing is checked. Shown as
    DEMO DATA in the Studio.
    """

    def validate(self, file: ExperimentFile, level: str = "full") -> ValidationReport:
        """Sample-data version of ``ValidationService.validate``."""
        findings = [
            Finding(
                code="TIME_RESOLUTION_AGGREGATED",
                severity=Severity.INFO,
                area="time",
                path="time.resolution",
                message="Hourly aggregation of 15-min profiles (energy-consistent mean of 4 rows).",
            ),
            Finding(
                code="DATA_STATUS_RECONSTRUCTED",
                severity=Severity.WARNING,
                area="data",
                path="meta.data_status",
                message="Case 6 profile mapping is unpublished; results are labelled reconstructed-unverified.",
                fix_hint="Keep the label in all figures.",
            ),
            Finding(
                code="BATTERY_NO_POWER_LIMIT",
                severity=Severity.WARNING,
                area="participants",
                path="participants[0].battery.max_power_kw",
                message="Battery has no power limit (I-71).",
                fix_hint="Set max_power_kw.",
            ),
        ]
        if not file.participants:
            findings.append(
                Finding(
                    code="PARTICIPANTS_EMPTY",
                    severity=Severity.ERROR,
                    area="participants",
                    path="participants",
                    message="No participants defined.",
                    fix_hint="Add participants or a placement rule.",
                )
            )
        return ValidationReport(
            file_hash=DemoConfigService().hash(file)[:12],
            level=level,
            findings=findings,
        )

    def dry_run(self, file: ExperimentFile) -> DryRunResult:
        """Sample-data version of ``ValidationService.dry_run``."""
        return DryRunResult(
            ok=True,
            observation_dims={p["id"]: 50 for p in file.participants},
            power_flow_converged=True,
            settlement_residual_kwh=0.0,
            messages=["Demo dry run: no environment was built."],
        )
