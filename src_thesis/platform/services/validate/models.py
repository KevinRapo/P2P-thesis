"""Data types of the Validate page: findings, dry run and sanity scenarios."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from src_thesis.platform.services.models import Series


class Severity(str, Enum):
    """How serious a validation finding is; errors block a launch."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Finding(BaseModel):
    """One validation finding.

    Attributes:
        code: Stable identifier, e.g. ``"GRID_MAPPING_DUPLICATE_OWNER"``.
        severity: Error, warning or info.
        area: Schema, data, grid mapping, time, protocol or resources.
        path: Dotted path of the field, so the Studio can jump to it.
        message: What is wrong.
        fix_hint: How to fix it.
    """

    code: str
    severity: Severity
    area: str
    path: str
    message: str
    fix_hint: str = ""


class ValidationReport(BaseModel):
    """All findings of one validation.

    Attributes:
        file_hash: Canonical hash of the validated file.
        level: ``"schema"``, ``"references"`` or ``"full"``.
        findings: The findings.
    """

    file_hash: str
    level: Literal["schema", "references", "full"]
    findings: list[Finding] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when there is no error (warnings are allowed)."""
        return not any(f.severity == Severity.ERROR for f in self.findings)


class DryRunResult(BaseModel):
    """Outcome of building the environment and taking one step.

    Attributes:
        ok: Whether the step succeeded.
        observation_dims: Observation size per agent.
        power_flow_converged: Whether the first power flow converged.
        settlement_residual_kwh: Energy-balance residual of the settlement (should be
            ~0).
        messages: What was checked and found.
    """

    ok: bool
    observation_dims: dict[str, int] = Field(default_factory=dict)
    power_flow_converged: bool | None = None
    settlement_residual_kwh: float | None = None
    messages: list[str] = Field(default_factory=list)


class Expectation(BaseModel):
    """One statement of a sanity scenario and whether it held."""

    statement: str
    passed: bool
    detail: str = ""


class ScenarioInfo(BaseModel):
    """A sanity scenario: what it does and what must happen."""

    id: str
    title: str
    expected: str


class ScenarioOutcome(BaseModel):
    """The result of running a sanity scenario.

    Attributes:
        scenario: Scenario ID.
        title: Its title.
        expected: What it expected, in words.
        passed: Whether every statement held.
        expectations: Each statement with the numbers behind it.
        series: Voltage per hour with and without the scenario, for a chart.
        error: Set instead of the rest when the scenario could not run.
    """

    scenario: str
    title: str = ""
    expected: str = ""
    passed: bool = False
    expectations: list[Expectation] = Field(default_factory=list)
    series: Series | None = None
    error: str = ""
