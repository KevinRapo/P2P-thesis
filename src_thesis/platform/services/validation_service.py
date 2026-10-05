"""ValidationService: preflight checks before any run (04 §5, 02 §9).

Three kinds of checks: the file itself (``validate``), building one step of the
world (``dry_run``) and the sanity scenarios (``run_scenario``). The last two need
the market and the network, so they run in a subprocess and the Studio stays free of
them.
"""

from __future__ import annotations

from src_thesis.marlem.core.scenarios import INFO
from src_thesis.platform.experiments.models.files import canonical_hash
from src_thesis.platform.experiments.models.resolve import resolve
from src_thesis.platform.experiments.runners.probe import run_probe
from src_thesis.platform.services.models import (
    DryRunResult,
    Expectation,
    ExperimentFile,
    Finding,
    ScenarioInfo,
    ScenarioOutcome,
    Series,
    Severity,
    ValidationReport,
)

SIMULATED_PROFILE_SOURCES = ("native", "catalog")


def _finding(code, severity, area, path, message, fix=""):
    return Finding(
        code=code,
        severity=severity,
        area=area,
        path=path,
        message=message,
        fix_hint=fix,
    )


class ValidationService:
    """Preflight checks before any run (02 §9)."""

    SAMPLE_DATA = False

    def validate(self, file: ExperimentFile, level: str = "full") -> ValidationReport:
        """Check a file and report findings with the field they concern.

        Args:
            file: The file to check.
            level: ``"schema"`` (the file alone, instant), ``"references"`` or
                ``"full"`` (also that the buses and elements exist in the network).
        """
        findings = self._schema(file)
        if level in ("references", "full"):
            findings += self._references(file)
        return ValidationReport(
            file_hash=canonical_hash(file)[:12], level=level, findings=findings
        )

    def _schema(self, file: ExperimentFile) -> list[Finding]:
        E, W, I = Severity.ERROR, Severity.WARNING, Severity.INFO
        out: list[Finding] = []
        try:
            r = resolve(file)
        except NotImplementedError as error:
            return [
                _finding(
                    "PLACEMENT_RULE", E, "participants", "participants", str(error)
                )
            ]
        source = r.grid.source
        if source is None or not source.code:
            out.append(
                _finding(
                    "GRID_SOURCE_MISSING",
                    E,
                    "grid",
                    "grid.source",
                    "No network is chosen.",
                    "Pick a network on the Grid page.",
                )
            )
        if not r.participants:
            out.append(
                _finding(
                    "PARTICIPANTS_EMPTY",
                    E,
                    "participants",
                    "participants",
                    "No participants defined.",
                    "Add participants on the Participants page.",
                )
            )
        seen: dict[str, int] = {}
        owners: dict[str, str] = {}
        for i, p in enumerate(r.participants):
            where = f"participants[{i}]"
            if p.id in seen:
                out.append(
                    _finding(
                        "PARTICIPANT_DUPLICATE_ID",
                        E,
                        "participants",
                        f"{where}.id",
                        f"The ID {p.id} is used twice.",
                    )
                )
            seen[p.id] = i
            if not p.bus:
                out.append(
                    _finding(
                        "PARTICIPANT_NO_BUS",
                        E,
                        "participants",
                        f"{where}.bus",
                        f"{p.id} sits on no bus.",
                    )
                )
            for kind in ("loads", "sgens", "storage"):
                for element in getattr(p.owns, kind, None) or []:
                    if owners.setdefault(element, p.id) != p.id:
                        out.append(
                            _finding(
                                "GRID_MAPPING_DUPLICATE_OWNER",
                                E,
                                "participants",
                                f"{where}.owns.{kind}",
                                f"{element} belongs to both {owners[element]} and "
                                f"{p.id}.",
                            )
                        )
            profile_source = (p.profile.source if p.profile else None) or "native"
            if profile_source not in SIMULATED_PROFILE_SOURCES:
                out.append(
                    _finding(
                        "PROFILE_SOURCE_UNSUPPORTED",
                        E,
                        "participants",
                        f"{where}.profile.source",
                        f"{p.id}: profiles from {profile_source} cannot be "
                        "simulated yet.",
                        "Use native or catalog profiles.",
                    )
                )
            if (
                p.battery
                and p.battery.nominal_capacity_kwh
                and not p.battery.max_power_kw
            ):
                out.append(
                    _finding(
                        "BATTERY_NO_POWER_LIMIT",
                        W,
                        "participants",
                        f"{where}.battery.max_power_kw",
                        f"{p.id}: the battery has no power limit (I-71); the "
                        "simulation will show it as an engine fault when it is "
                        "exceeded.",
                        "Set max_power_kw.",
                    )
                )
        m = r.market
        if m.price.max <= m.price.min:
            out.append(
                _finding(
                    "MARKET_PRICE_BOUNDS",
                    E,
                    "market",
                    "market.price",
                    "The largest price must be above the smallest.",
                )
            )
        if m.quantity.max <= m.quantity.min:
            out.append(
                _finding(
                    "MARKET_QUANTITY_BOUNDS",
                    E,
                    "market",
                    "market.quantity",
                    "The largest quantity must be above the smallest.",
                )
            )
        t = r.dso.tariffs
        if t.source == "csv" and not (
            t.feed_in and t.feed_in.path and t.utility and t.utility.path
        ):
            out.append(
                _finding(
                    "TARIFF_CSV_NO_PATH",
                    W,
                    "dso",
                    "dso.tariffs",
                    "Tariffs come from CSV but no files are set; synthetic "
                    "tariffs are used instead.",
                    "Pick the tariff files on the Market & DSO page.",
                )
            )
        out.append(
            _finding(
                "TIME_RESOLUTION",
                I,
                "time",
                "time.resolution",
                f"Time resolution: {r.time.resolution}.",
            )
        )
        if r.meta.data_status != "measured":
            out.append(
                _finding(
                    "DATA_STATUS",
                    W,
                    "data",
                    "meta.data_status",
                    f"Data status is {r.meta.data_status}; keep the label in "
                    "every figure.",
                )
            )
        return out

    def _references(self, file: ExperimentFile) -> list[Finding]:
        from src_thesis.marlem.grid import contract, simbench

        E = Severity.ERROR
        r = resolve(file)
        source = r.grid.source
        if source is None or not source.code:
            return []
        try:
            ref = contract.NetworkRef(source.type, source.code)
            buses = {b.id for b in simbench.topology_view(ref).buses}
            elements = {e.id for e in simbench.elements(ref)}
        except Exception as error:  # noqa: BLE001  any load failure is a finding
            return [
                _finding(
                    "GRID_NOT_FOUND",
                    E,
                    "grid",
                    "grid.source",
                    f"The network cannot be loaded: {error}",
                )
            ]
        out = []
        for i, p in enumerate(r.participants):
            if p.bus and p.bus not in buses:
                out.append(
                    _finding(
                        "PARTICIPANT_BUS_UNKNOWN",
                        E,
                        "participants",
                        f"participants[{i}].bus",
                        f"{p.id}: bus {p.bus} is not in the network.",
                    )
                )
            for kind in ("loads", "sgens", "storage"):
                for element in getattr(p.owns, kind, None) or []:
                    if element not in elements:
                        out.append(
                            _finding(
                                "PARTICIPANT_ELEMENT_UNKNOWN",
                                E,
                                "participants",
                                f"participants[{i}].owns.{kind}",
                                f"{p.id}: {element} is not in the network.",
                            )
                        )
        return out

    def dry_run(self, file: ExperimentFile) -> DryRunResult:
        """Build one day, take the first step with nobody ordering, assess the grid.

        Runs in a subprocess; it takes some seconds.
        """
        out = run_probe("dry-run", file.model_dump_json(exclude_unset=True))
        if "error" in out:
            return DryRunResult(ok=False, messages=[out["error"]])
        return DryRunResult(
            ok=out["ok"],
            power_flow_converged=out["power_flow_converged"],
            settlement_residual_kwh=out["settlement_residual_kwh"],
            messages=out["messages"],
        )

    def scenarios(self) -> list[ScenarioInfo]:
        """The sanity scenarios and what each expects."""
        return [ScenarioInfo(id=k, title=t, expected=e) for k, (t, e) in INFO.items()]

    def run_scenario(self, file: ExperimentFile, scenario_id: str) -> ScenarioOutcome:
        """Run one sanity scenario on the file's network and participants.

        Runs in a subprocess; it takes some seconds.
        """
        if scenario_id not in INFO:
            raise ValueError(f"Unknown scenario {scenario_id!r}")
        out = run_probe(
            "scenario", file.model_dump_json(exclude_unset=True), scenario_id
        )
        if "error" in out:
            title, expected = INFO[scenario_id]
            return ScenarioOutcome(
                scenario=scenario_id, title=title, expected=expected, error=out["error"]
            )
        return ScenarioOutcome(
            scenario=out["scenario"],
            title=out["title"],
            expected=out["expected"],
            passed=out["passed"],
            expectations=[Expectation(**e) for e in out["expectations"]],
            series=Series(
                x=out["hours"],
                y={
                    k: [v if v is not None else float("nan") for v in vs]
                    for k, vs in out["series"].items()
                },
                x_label="hour",
                y_label="voltage (pu)",
            ),
        )
