"""Demo implementations of the application services.

They return deterministic sample data so the Studio can be built and reviewed
before the real services exist. Nothing here imports MARLEM, pandapower or Ray.
Every value is illustrative and labelled as demo data in the UI.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

from .models import (
    DryRunResult,
    ElementInfo,
    ExperimentFile,
    ExperimentMeta,
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
    RunState,
    RunStatus,
    RunSummary,
    Series,
    Severity,
    TopologyView,
    ValidationReport,
)

PARADIGMS = ["ctce", "ctde", "dtde"]
ALGORITHMS = ["ppo", "appo", "sac"]
HOURS = list(range(24))
_NOW = datetime(2026, 9, 23, 12, 0)


def _default_learning() -> dict:
    """Original MARLEM defaults, see 02-experiment-config.md §3.8."""
    return {
        "paradigms": list(PARADIGMS),
        "algorithms": list(ALGORITHMS),
        "seeds": [1, 2, 3],
        "budget": {"unit": "env_steps", "value": 2_000_000},
        "paradigm_options": {
            "ctce": {"reward_aggregation": "sum"},
            "ctde": {"reward_aggregation": "sum"},
            "dtde": {"policy_sharing": "independent"},
        },
        "model": {"embeddings_dim": 128, "activation": "relu"},
        "algorithm_params": {
            "ppo": {
                "lr": 1e-5,
                "gamma": 0.99,
                "lambda_": 0.95,
                "num_epochs": 30,
                "minibatch_size": 128,
                "clip_param": 0.2,
                "entropy_coeff": 0.01,
                "kl_coeff": 0.0,
                "grad_clip": 0.5,
            },
            "appo": {
                "lr": 1e-5,
                "gamma": 0.99,
                "lambda_": 0.95,
                "vtrace": True,
                "entropy_coeff": 0.01,
                "kl_coeff": 0.0,
                "grad_clip": 0.5,
            },
            "sac": {
                "actor_lr": 1e-5,
                "critic_lr": 1e-5,
                "gamma": 0.99,
                "twin_q": True,
                "target_entropy": "auto",
                "replay_buffer": {"capacity": 1000},
                "grad_clip": 0.5,
            },
        },
        "tuning": {"method": "none", "num_samples": 1},
        "checkpoint": {"every": 10, "keep": 3},
    }


def _participants(n: int = 8) -> list[dict]:
    roles = [
        ("small_industry", "G1-A", "PV3", 180),
        ("community_hospital", "G3-A", "PV2", 170),
        ("university_campus", "G2-A", "PV4", 140),
        ("shopping_mall", "G4-A", "PV1", 130),
        ("residential_complex", "H0-B", "PV5", 80),
        ("apartment_building", "H0-A", "PV6", 75),
        ("community_solar_farm", "H0-C", "PV8", 180),
        ("parking_lot", "G6-A", "PV7", 160),
    ]
    out = []
    for i, (role, demand, gen, peak) in enumerate(roles[:n]):
        out.append(
            {
                "id": role,
                "role": role,
                "bus": f"LV4.101 Bus {10 + 3 * i}",
                "owns": {"loads": [f"LV4.101 Load {5 + 2 * i}"], "sgens": []},
                "profile": {
                    "source": "catalog",
                    "demand": {"type": demand},
                    "generation": {"type": gen},
                },
                "scaling": {"mode": "peak_kw", "demand": peak, "generation": peak},
                "battery": (
                    {
                        "nominal_capacity_kwh": round(peak * 0.6, 1),
                        "min_soc": 0.1,
                        "max_soc": 0.9,
                        "charge_efficiency": 0.95,
                        "discharge_efficiency": 0.95,
                    }
                    if i % 3 != 2
                    else None
                ),
            }
        )
    return out


_PRESETS = {
    "case1-mechanisms": ("Case 1: market mechanisms", "sweep: market.mechanism (6)"),
    "case2-heterogeneity": ("Case 2: agent heterogeneity", "sweep: participant sizes"),
    "case3-dso-strategies": ("Case 3: DSO strategies", "sweep: DSO fees and tariffs"),
    "case4-grid-constraints": (
        "Case 4: grid constraints",
        "sweep: feeder, SimBench scenario, background",
    ),
    "case5-battery": (
        "Case 5: battery coordination",
        "sweep: batteries none vs strategic",
    ),
    "case6-3x3": (
        "Case 6: implicit cooperation (3 × 3)",
        "paradigms × algorithms × seeds",
    ),
    "case7-scalability": ("Case 7: scalability", "sweep: number of agents"),
}


def _preset_file(preset_id: str) -> ExperimentFile:
    name, description = _PRESETS[preset_id]
    return ExperimentFile(
        meta=ExperimentMeta(
            id=preset_id,
            name=name,
            description=description,
            tags=["preset", "paper"],
            derived_from=f"preset:{preset_id}",
            data_status=(
                "reconstructed-unverified" if preset_id == "case6-3x3" else "synthetic"
            ),
        ),
        time={
            "resolution": "hourly_aggregated",
            "horizon_steps": 24,
            "days": {
                "mode": "sampler",
                "start": "2016-05-01",
                "end": "2016-08-31",
                "filter": {"day_type": "workday"},
                "eval_holdout": 0.2,
                "seed": 42,
            },
        },
        grid={
            "source": {"type": "simbench", "code": "1-LV-semiurb4--0-sw"},
            "background": {"mode": "mapped_replacement"},
            "limits": {
                "v_min_pu": 0.95,
                "v_max_pu": 1.05,
                "line_max_percent": 100,
                "trafo_max_percent": 100,
            },
            "ratings": {"source": "network"},
            "assessment": {"mode": "feedback", "non_convergence": "truncate_episode"},
        },
        participants=_participants(),
        market={
            "mechanism": "average",
            "price": {"min": 20, "max": 600},
            "quantity": {"min": 0, "max": 180},
            "partner_preference": False,
            "ledger": {"enabled": True, "difficulty": 0},
            "async_orders": True,
        },
        dso={
            "tariffs": {"source": "csv", "mode": "normalized"},
            "fees": {
                "charged": True,
                "congestion_factor": 0.5,
                "congestion_threshold": 0.8,
                "distance_factor": 0.35,
                "voltage_factor": 0.15,
                "voltage_threshold": 0.05,
                "instability_threshold": 0.2,
                "imbalance_factor": 0.15,
                "zone_factor": 0.15,
            },
        },
        environment={
            "observation": {
                "version": "v2-grid",
                "forecast_error": 0.3,
                "own_bus_voltage": "private",
            },
            "reward": {
                "version": "corrected-v1",
                "log_scale": 20,
                "grid_violation": {"attribution": "bus"},
            },
            "reputation": {
                "weights": {"reliability": 0.3, "fairness": 0.2, "grid": 0.5}
            },
        },
        learning=_default_learning(),
        evaluation={
            "interval": 10,
            "episodes": 20,
            "days": "holdout",
            "explore": False,
        },
        baselines=["no_order", "random"],
        sweep=(
            {
                "mode": "grid",
                "parameters": {
                    "market.mechanism": [
                        "average",
                        "buyer",
                        "seller",
                        "bid_ask_spread",
                        "nash_bargaining",
                        "proportional_surplus",
                    ]
                },
            }
            if preset_id == "case1-mechanisms"
            else {}
        ),
        resources={"cpus_per_run": 6, "gpus_per_learner": 0, "max_parallel_runs": 1},
        outputs={"record_steps": "evaluation", "grid_element_results": False},
    )


class DemoConfigService:
    """Demo ``ConfigService``: experiment files kept in memory; presets built in code.
    Shown as DEMO DATA in the Studio.
    """
    def __init__(self) -> None:
        self._drafts: dict[str, ExperimentFile] = {}

    def list(self, kind: str | None = None) -> list[FileSummary]:
        """Sample-data version of ``ConfigService.list``."""
        items = [
            FileSummary(
                id=pid,
                name=name,
                kind="preset",
                path=f"experiments/presets/{pid}.marlem.json",
                modified=_NOW - timedelta(days=i),
                tags=["paper"],
                network="1-LV-semiurb4--0-sw",
                participants=8,
            )
            for i, (pid, (name, _)) in enumerate(_PRESETS.items())
        ]
        items += [
            FileSummary(
                id=d.meta.id,
                name=d.meta.name,
                kind="draft",
                path=f"experiments/user/{d.meta.id}.marlem.json",
                modified=_NOW,
                network=d.grid.get("source", {}).get("code", ""),
                participants=len(d.participants),
            )
            for d in self._drafts.values()
        ]
        return [i for i in items if kind is None or i.kind == kind]

    def load(self, file_id: str) -> ExperimentFile:
        """Sample-data version of ``ConfigService.load``."""
        return self._drafts.get(file_id) or _preset_file(
            file_id if file_id in _PRESETS else "case6-3x3"
        )

    def new_from_preset(self, preset_id: str) -> ExperimentFile:
        """Sample-data version of ``ConfigService.new_from_preset``."""
        file = _preset_file(preset_id)
        file.meta.id = f"{preset_id}-draft"
        file.meta.tags = ["draft"]
        self._drafts[file.meta.id] = file
        return file

    def save(self, file: ExperimentFile, path: Path | None = None) -> str:
        """Sample-data version of ``ConfigService.save``."""
        self._drafts[file.meta.id] = file
        return str(path or f"experiments/user/{file.meta.id}.marlem.json")

    def clone(self, file_id: str, new_id: str) -> ExperimentFile:
        """Sample-data version of ``ConfigService.clone``."""
        file = self.load(file_id).model_copy(deep=True)
        file.meta.id, file.meta.derived_from = new_id, file_id
        self._drafts[new_id] = file
        return file

    def delete(self, file_id: str) -> None:
        """Sample-data version of ``ConfigService.delete``."""
        self._drafts.pop(file_id, None)

    def update(self, file: ExperimentFile, changes: dict) -> ExperimentFile:
        """Sample-data version of ``ConfigService.update``."""
        data = file.model_dump(mode="json")
        for path, value in changes.items():
            node = data
            *parents, leaf = path.split(".")
            for key in parents:
                node = node.setdefault(key, {})
            node[leaf] = value
        return ExperimentFile.model_validate(data)

    def origin(self, file: ExperimentFile) -> ExperimentFile | None:
        """Sample-data version of ``ConfigService.origin``."""
        source = (file.meta.derived_from or "").removeprefix("preset:")
        return _preset_file(source) if source in _PRESETS else None

    def resolve(self, file: ExperimentFile) -> ExperimentFile:
        """Sample-data version of ``ConfigService.resolve``."""
        return file

    def expand(self, file: ExperimentFile) -> list[RunCell]:
        """Sample-data version of ``ConfigService.expand``."""
        learning = file.learning or _default_learning()
        points = 1
        for values in file.sweep.get("parameters", {}).values():
            points *= len(values)
        return [
            RunCell(
                sweep_label=f"p{p}" if points > 1 else "",
                algorithm=a,
                paradigm=m,
                seed=s,
            )
            for p in range(points)
            for m in learning["paradigms"]
            for a in learning["algorithms"]
            for s in learning["seeds"]
        ]

    def hash(self, file: ExperimentFile) -> str:
        """Sample-data version of ``ConfigService.hash``."""
        return hashlib.sha256(self.to_json(file).encode()).hexdigest()

    def diff(self, a: ExperimentFile, b: ExperimentFile) -> list[FieldChange]:
        """Sample-data version of ``ConfigService.diff``."""
        da, db = a.model_dump(), b.model_dump()
        return [
            FieldChange(path=k, before=da[k], after=db[k]) for k in da if da[k] != db[k]
        ]

    def export_bundle(self, file: ExperimentFile) -> str:
        """Sample-data version of ``ConfigService.export_bundle``."""
        return f"exports/{file.meta.id}.zip"

    def to_json(self, file: ExperimentFile) -> str:
        """Sample-data version of ``ConfigService.to_json``."""
        return json.dumps(
            file.model_dump(mode="json"), indent=2, sort_keys=False, ensure_ascii=False
        )


_NETWORKS = [
    ("simbench", "1-LV-rural1--0-sw", "LV rural 1", "LV", 15, 13, 4, 0, True, True),
    (
        "simbench",
        "1-LV-semiurb4--0-sw",
        "LV semi-urban 4",
        "LV",
        44,
        41,
        12,
        0,
        True,
        True,
    ),
    ("simbench", "1-LV-urban6--0-sw", "LV urban 6", "LV", 59, 111, 10, 0, True, True),
    (
        "simbench",
        "1-MV-rural--1-sw",
        "MV rural, scenario 1",
        "MV",
        99,
        118,
        102,
        0,
        True,
        True,
    ),
    (
        "pandapower_builtin",
        "case33bw",
        "IEEE 33-bus (Baran & Wu)",
        "MV",
        33,
        32,
        0,
        0,
        False,
        False,
    ),
    (
        "pandapower_builtin",
        "cigre_mv",
        "CIGRE MV with DER",
        "MV",
        15,
        18,
        9,
        2,
        False,
        True,
    ),
    ("pandapower_builtin", "cigre_lv", "CIGRE LV", "LV", 44, 15, 0, 0, False, True),
    (
        "pandapower_builtin",
        "mv_oberrhein",
        "MV Oberrhein",
        "MV",
        179,
        147,
        153,
        0,
        False,
        True,
    ),
]


class DemoGridCatalogService:
    """Demo ``GridCatalogService``: a few sample networks with generated topology. Shown
    as DEMO DATA in the Studio.
    """
    def list_networks(
        self, source_type: str | None = None, level: str | None = None
    ) -> list[NetworkInfo]:
        """Sample-data version of ``GridCatalogService.list_networks``."""
        out = []
        for (
            t,
            code,
            label,
            lvl,
            buses,
            loads,
            sgens,
            storage,
            profiles,
            ratings,
        ) in _NETWORKS:
            if (source_type and t != source_type) or (level and lvl != level):
                continue
            out.append(
                NetworkInfo(
                    source=NetworkSource(type=t, code=code),
                    label=label,
                    voltage_level=lvl,
                    buses=buses,
                    loads=loads,
                    sgens=sgens,
                    storage=storage,
                    has_profiles=profiles,
                    has_line_ratings=ratings,
                    has_geodata=True,
                )
            )
        return out

    def _info(self, source: NetworkSource) -> NetworkInfo:
        return next(
            (n for n in self.list_networks() if n.source.code == source.code),
            self.list_networks()[1],
        )

    def summary(self, source: NetworkSource) -> NetworkSummary:
        """Sample-data version of ``GridCatalogService.summary``."""
        info = self._info(source)
        return NetworkSummary(
            info=info,
            total_load_kw=round(info.loads * 7.5, 1),
            total_generation_kw=round(info.sgens * 9.0, 1),
            lines=info.buses - 1,
            transformers=1,
        )

    def topology(self, source: NetworkSource) -> TopologyView:
        """A deterministic radial feeder layout sized like the selected network."""
        n = min(self._info(source).buses, 60)
        rng = random.Random(n)
        buses = [{"id": "Bus 0", "x": 0.0, "y": 0.0, "kind": "external_grid"}]
        lines, feeders = [], 4
        for i in range(1, n):
            feeder = (i - 1) % feeders
            depth = (i - 1) // feeders + 1
            angle = (feeder - (feeders - 1) / 2) * 0.55 + rng.uniform(-0.08, 0.08)
            buses.append(
                {
                    "id": f"Bus {i}",
                    "x": depth * math.cos(angle),
                    "y": depth * math.sin(angle) * 2.2,
                    "kind": "load" if i % 3 else "load+pv",
                }
            )
            parent = 0 if depth == 1 else i - feeders
            lines.append({"id": f"Line {i}", "from": f"Bus {parent}", "to": f"Bus {i}"})
        return TopologyView(buses=buses, lines=lines, external_grid_bus="Bus 0")

    def elements(
        self, source: NetworkSource, bus: str | None = None
    ) -> list[ElementInfo]:
        """Sample-data version of ``GridCatalogService.elements``."""
        topo = self.topology(source)
        out = []
        for i, b in enumerate(topo.buses[1:], start=1):
            out.append(
                ElementInfo(
                    id=f"Load {i}",
                    element_type="load",
                    bus=b["id"],
                    profile_type=["H0-A", "H0-B", "G1-A", "L0-A"][i % 4],
                    rated_kw=round(4 + (i % 7) * 1.5, 1),
                )
            )
            if b["kind"] == "load+pv":
                out.append(
                    ElementInfo(
                        id=f"PV {i}",
                        element_type="sgen",
                        bus=b["id"],
                        profile_type=f"PV{1 + i % 8}",
                        rated_kw=round(5 + (i % 5) * 2.0, 1),
                    )
                )
        return [e for e in out if bus is None or e.bus == bus]

    def preview_powerflow(
        self, source: NetworkSource, day: str, step: int
    ) -> PowerFlowPreview:
        """Sample-data version of ``GridCatalogService.preview_powerflow``."""
        topo = self.topology(source)
        load = 0.6 + 0.4 * math.sin(math.pi * step / 24)
        volts = {
            b["id"]: round(1.02 - 0.012 * math.hypot(b["x"], b["y"]) * load, 4)
            for b in topo.buses
        }
        vmin = min(volts.values())
        return PowerFlowPreview(
            converged=True,
            min_voltage_pu=vmin,
            max_voltage_pu=max(volts.values()),
            max_line_loading_percent=round(55 + 40 * load, 1),
            losses_kw=round(12 * load, 2),
            bus_voltage_pu=volts,
            violations=[f"V_LOW at {k}" for k, v in volts.items() if v < 0.95][:5],
        )


class DemoProfileService:
    """Demo ``ProfileService``: generated sample curves. Shown as DEMO DATA in the
    Studio.
    """
    def profile_types(self, source: NetworkSource | None = None) -> list[ProfileType]:
        """Sample-data version of ``ProfileService.profile_types``."""
        return (
            [
                ProfileType(
                    code=f"H0-{c}", category="household", description="Household"
                )
                for c in "ABCDEFGHIJKL"
            ]
            + [
                ProfileType(
                    code=f"G{i}-A", category="commercial", description="Commercial"
                )
                for i in range(7)
            ]
            + [
                ProfileType(
                    code=f"L{i}-A", category="agricultural", description="Agricultural"
                )
                for i in range(3)
            ]
            + [
                ProfileType(code=f"PV{i}", category="pv", description="Photovoltaic")
                for i in range(1, 9)
            ]
            + [
                ProfileType(code="WP4", category="wind", description="Wind"),
                ProfileType(code="BM1", category="biomass", description="Biomass"),
            ]
        )

    def preview(self, file: ExperimentFile, participant_id: str) -> Series:
        """Sample-data version of ``ProfileService.preview``."""
        p = next(
            (x for x in file.participants if x["id"] == participant_id),
            file.participants[0] if file.participants else {},
        )
        peak = float(p.get("scaling", {}).get("generation", 100))
        gen = [
            round(max(0.0, peak * math.exp(-(((h - 12.5) / 3.2) ** 2))), 1)
            for h in HOURS
        ]
        dem = [
            round(
                peak
                * (
                    0.35
                    + 0.25 * math.exp(-(((h - 8) / 2) ** 2))
                    + 0.35 * math.exp(-(((h - 19) / 2.5) ** 2))
                ),
                1,
            )
            for h in HOURS
        ]
        return Series(
            x=HOURS,
            y={
                "generation": gen,
                "demand": dem,
                "net": [round(g - d, 1) for g, d in zip(gen, dem)],
            },
            x_label="hour",
            y_label="kW",
        )

    def suggest_mapping(self, source: NetworkSource, rule: dict) -> list[dict]:
        """Sample-data version of ``ProfileService.suggest_mapping``."""
        return _participants(int(rule.get("n", 8)))

    def days(self, file: ExperimentFile) -> dict[str, list[str]]:
        """Sample-data version of ``ProfileService.days``."""
        start = datetime(2016, 5, 2)
        days = [
            (start + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(0, 120)
            if (start + timedelta(days=i)).weekday() < 5
        ]
        cut = int(len(days) * 0.8)
        return {"train": days[:cut], "eval": days[cut:]}

    def tariffs(self, file: ExperimentFile) -> Series:
        """Sample-data version of ``ProfileService.tariffs``."""
        fit = [
            round(40 + 25 * math.sin(math.pi * (h - 6) / 12) if 6 <= h <= 18 else 35, 1)
            for h in HOURS
        ]
        util = [
            round(v * 2.4 + (60 if 17 <= h <= 21 else 0), 1) for h, v in zip(HOURS, fit)
        ]
        return Series(
            x=HOURS,
            y={"feed-in tariff": fit, "utility price": util},
            x_label="hour",
            y_label="price",
        )


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


class DemoExperimentService:
    """Demo ``ExperimentService``: invented runs; nothing is started. Shown as DEMO DATA
    in the Studio.
    """
    def __init__(self) -> None:
        self._runs = self._seed_runs()

    @staticmethod
    def _seed_runs() -> list[RunSummary]:
        states = [RunState.COMPLETED] * 5 + [
            RunState.RUNNING,
            RunState.RUNNING,
            RunState.QUEUED,
            RunState.FAILED,
        ]
        runs = []
        for i, (m, a) in enumerate((m, a) for m in PARADIGMS for a in ALGORITHMS):
            state = states[i]
            progress = {
                RunState.COMPLETED: 1.0,
                RunState.RUNNING: 0.35 + 0.2 * i / 9,
                RunState.QUEUED: 0.0,
                RunState.FAILED: 0.62,
            }[state]
            runs.append(
                RunSummary(
                    run_id=f"case6-3x3__{a}-{m}__s1__{1000 + i:x}",
                    experiment_id="case6-3x3",
                    cell=RunCell(algorithm=a, paradigm=m, seed=1),
                    network="1-LV-semiurb4--0-sw",
                    state=state,
                    progress=round(progress, 2),
                    started=_NOW - timedelta(hours=9 - i),
                    elapsed_s=3600 * (9 - i) * progress,
                    eta_s=3600 * 2.5 if state == RunState.RUNNING else None,
                )
            )
        return runs

    def create_runs(self, file: ExperimentFile) -> list[str]:
        """Sample-data version of ``ExperimentService.create_runs``."""
        return [
            f"{file.meta.id}__{c.algorithm}-{c.paradigm}__s{c.seed}"
            for c in DemoConfigService().expand(file)
        ]

    def start(self, run_ids: list[str]) -> None:
        """Sample-data version of ``ExperimentService.start``."""
        return None

    def cancel(self, run_id: str) -> None:
        """Sample-data version of ``ExperimentService.cancel``."""
        return None

    def snapshot(self, run_id: str) -> RunStatus:
        """Sample-data version of ``ExperimentService.snapshot``."""
        run = next((r for r in self._runs if r.run_id == run_id), self._runs[0])
        it = int(run.progress * 200)
        return RunStatus(
            summary=run,
            iteration=it,
            last_metrics={
                "episode_return_mean": round(-40 + 60 * run.progress, 2),
                "violations_per_episode": round(8 * (1 - run.progress), 2),
            },
            log_tail=[
                f"[iter {max(0, it - k)}] episode_return_mean={-40 + 60 * run.progress - k:.2f}"
                for k in range(5, 0, -1)
            ],
        )

    def list_runs(self, experiment_id: str | None = None) -> list[RunSummary]:
        """Sample-data version of ``ExperimentService.list_runs``."""
        return [
            r
            for r in self._runs
            if experiment_id is None or r.experiment_id == experiment_id
        ]

    def estimate(self, file: ExperimentFile) -> RunEstimate:
        """Sample-data version of ``ExperimentService.estimate``."""
        n = len(DemoConfigService().expand(file))
        return RunEstimate(
            runs=n,
            estimated_hours=round(n * 3.2, 1),
            note="Demo estimate from placeholder benchmarks.",
        )

    def health(self) -> RepositoryHealth:
        """Sample-data version of ``ExperimentService.health``."""
        return RepositoryHealth(
            git_dirty=True,
            validation_progress=0.0,
            dependencies_ok=True,
            messages=[
                "Demo services active: no MARLEM code is executed.",
                "Validation plan: 0 of 80 issues closed.",
            ],
        )


class DemoResultService:
    """Demo ``ResultService``: generated sample results. Shown as DEMO DATA in the
    Studio.
    """
    def summary(self, run_id: str) -> RunResult:
        """Sample-data version of ``ResultService.summary``."""
        rng = random.Random(run_id)
        return RunResult(
            run_id=run_id,
            rl_return=round(rng.uniform(5, 25), 2),
            outcomes={
                "served_demand_share": round(rng.uniform(0.9, 1.0), 3),
                "unmet_demand_kwh": round(rng.uniform(0, 40), 1),
                "curtailment_kwh": round(rng.uniform(0, 25), 1),
                "p2p_share": round(rng.uniform(0.2, 0.6), 3),
                "total_cost": round(rng.uniform(800, 1500), 0),
                "voltage_violations": rng.randint(0, 12),
                "losses_kwh": round(rng.uniform(10, 30), 1),
            },
            manifest={
                "network": "1-LV-semiurb4--0-sw",
                "reward.version": "corrected-v1",
                "data_status": "reconstructed-unverified",
                "commit": "demo",
            },
        )

    def training_curve(self, run_id: str) -> Series:
        """Sample-data version of ``ResultService.training_curve``."""
        rng = random.Random(run_id)
        it = list(range(0, 200, 5))
        train = [
            round(-40 + 55 * (1 - math.exp(-i / 60)) + rng.uniform(-3, 3), 2)
            for i in it
        ]
        ev = [round(v + rng.uniform(-2, 2), 2) for v in train]
        return Series(
            x=it,
            y={
                "train": train,
                "evaluation": ev,
                "no_order baseline": [-18.0] * len(it),
                "random baseline": [-9.0] * len(it),
            },
            x_label="iteration",
            y_label="episode return",
        )

    def step_records(self, run_id: str, episode: int = 0) -> list[dict]:
        """Sample-data version of ``ResultService.step_records``."""
        rng = random.Random(f"{run_id}-{episode}")
        return [
            {
                "step": t,
                "orders": 8,
                "p2p_trades": rng.randint(0, 6),
                "dso_trades": rng.randint(1, 8),
                "clearing_price": round(rng.uniform(80, 220), 1),
                "p2p_kwh": round(rng.uniform(0, 90), 1),
                "import_kwh": round(rng.uniform(-60, 120), 1),
                "min_v_pu": round(rng.uniform(0.93, 1.0), 3),
                "violations": rng.randint(0, 2),
            }
            for t in HOURS
        ]

    def grid_series(self, run_id: str, episode: int = 0) -> Series:
        """Sample-data version of ``ResultService.grid_series``."""
        vmin = [
            round(
                0.985
                - 0.04 * math.exp(-(((h - 19) / 2.5) ** 2))
                + 0.015 * math.exp(-(((h - 13) / 3) ** 2)),
                4,
            )
            for h in HOURS
        ]
        vmax = [
            round(1.01 + 0.035 * math.exp(-(((h - 13) / 3) ** 2)), 4) for h in HOURS
        ]
        load = [
            round(
                45
                + 35 * math.exp(-(((h - 19) / 3) ** 2))
                + 25 * math.exp(-(((h - 13) / 3) ** 2)),
                1,
            )
            for h in HOURS
        ]
        return Series(
            x=HOURS,
            y={
                "min voltage (pu)": vmin,
                "max voltage (pu)": vmax,
                "max line loading (%)": load,
            },
            x_label="hour",
            y_label="",
        )

    def agent_series(self, run_id: str, episode: int = 0) -> Series:
        """Sample-data version of ``ResultService.agent_series``."""
        return Series(
            x=HOURS,
            y={
                f"agent {i} SoC": [
                    round(0.5 + 0.35 * math.sin((h + 3 * i) / 24 * 2 * math.pi), 3)
                    for h in HOURS
                ]
                for i in range(4)
            },
            x_label="hour",
            y_label="state of charge",
        )

    def matrix(self, experiment_id: str, metric: str) -> MatrixTable:
        """Sample-data version of ``ResultService.matrix``."""
        rng = random.Random(f"{experiment_id}-{metric}")
        mean = [
            [round(rng.uniform(0.3, 0.9), 3) for _ in ALGORITHMS] for _ in PARADIGMS
        ]
        std = [
            [round(rng.uniform(0.01, 0.08), 3) for _ in ALGORITHMS] for _ in PARADIGMS
        ]
        return MatrixTable(
            metric=metric,
            rows=[p.upper() for p in PARADIGMS],
            columns=[a.upper() for a in ALGORITHMS],
            mean=mean,
            std=std,
        )

    def compare(self, run_ids: list[str], metric: str) -> Series:
        """Sample-data version of ``ResultService.compare``."""
        return Series(
            x=list(range(0, 200, 5)),
            y={r: self.training_curve(r).y["evaluation"] for r in run_ids},
            x_label="iteration",
            y_label=metric,
        )

    def export(self, run_ids: list[str], fmt: str = "csv") -> str:
        """Sample-data version of ``ResultService.export``."""
        return f"exports/{len(run_ids)}-runs.{fmt}"
