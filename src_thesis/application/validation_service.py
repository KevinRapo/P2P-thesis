"""ValidationService: preflight checks before any run (04 §5, 02 §9).

Every method still returns a fixed sample report; each docstring says what the
final version will check (R6-R7).
"""

from __future__ import annotations

from src_thesis.application.models import (
    DryRunResult,
    ExperimentFile,
    Finding,
    Severity,
    ValidationReport,
)
from src_thesis.experiments.models.files import canonical_hash


class ValidationService:
    """Preflight checks before any run (02 §9).

    Every method returns sample data until it is built; its docstring says what the
    final version will do.
    """

    SAMPLE_DATA = True  # shown in the Studio's header until the service is built

    def validate(self, file: ExperimentFile, level: str = "full") -> ValidationReport:
        """Check a file and report findings with the field they concern.

        Sample data for now. The final version will check schema (Pydantic), references,
        time, units, grid mapping, RL settings, protocol and resources, each finding
        with its field path.

        Args:
            file: The file to check.
            level: ``"schema"`` (instant), ``"references"`` (buses, files exist) or
                ``"full"`` (everything, including the dry run).
        """
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
            file_hash=canonical_hash(file)[:12],
            level=level,
            findings=findings,
        )

    def dry_run(self, file: ExperimentFile) -> DryRunResult:
        """Build the environment and take one step, to catch errors early.

        Sample data for now. The final version will build one environment with
        ``experiments.factory.environment.build_env`` and take one step with the no-
        order policy.
        """
        return DryRunResult(
            ok=True,
            observation_dims={p["id"]: 50 for p in file.participants},
            power_flow_converged=True,
            settlement_residual_kwh=0.0,
            messages=["Sample dry run: no environment was built."],
        )
