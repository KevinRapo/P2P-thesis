"""The only place that turns an experiment file into live MARLEM objects.

Why: in the original, the environment was assembled inside ``marl/train.py`` and the
notebooks, each with its own hard-coded values. Here there is exactly one function that
builds an environment from a file, used by the worker, the dry run, notebooks, tests and
every RLlib env runner. So whatever runs is exactly what the file says, and the same
file always gives the same environment.

RLlib env runners call the factory inside each runner; only the resolved file travels
in ``env_config``, never a network or agents.

Status: ``build_engine_spec`` and ``build_env`` build the original market for one day
(simulation, M2); the step-time grid model (``build_grid``) follows with M3/M4.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import src_thesis.marlem.grid.contract as contract
from src_thesis.marlem.core.engine import (
    AgentSpec,
    BatterySpec,
    EngineSpec,
    MarketSpec,
    TariffSpec,
)
from src_thesis.platform.experiments.factory.profiles import (
    RESOLUTIONS,
    participant_power,
    window_start,
)
from src_thesis.platform.experiments.models.records import ExperimentFile, RunCell
from src_thesis.platform.experiments.models.resolve import resolve_run

if TYPE_CHECKING:  # heavy imports stay out of this module at runtime
    from src_thesis.marlem.core.engine import MarketEngine
    from src_thesis.marlem.grid.contract import GridModel

ENV_CONFIG_KEY = "marlem_resolved_file"
# Fee settings of the file that are numbers on the DSO agent (``dso.fees``).
_FEE_NAMES = (
    "congestion_factor",
    "distance_factor",
    "zone_factor",
    "voltage_factor",
    "imbalance_factor",
    "congestion_threshold",
    "voltage_threshold",
    "instability_threshold",
)


def build_env_config(
    resolved: ExperimentFile,
    cell: RunCell,
    episode_seed: int | None = None,
    day: str | None = None,
) -> dict[str, Any]:
    """The ``env_config`` handed to RLlib: plain data only.

    Contains the resolved file (as a dict), the cell, the episode seed and the
    day, so every env runner can call :func:`build_env` on its own copy.
    """
    return {
        ENV_CONFIG_KEY: resolved.to_data(),
        "cell": cell.model_dump(mode="json"),
        "episode_seed": episode_seed,
        "day": day,
    }


def build_engine_spec(
    resolved: ExperimentFile, day: str | None = None, seed: int | None = None
) -> EngineSpec:
    """The world of one day as plain data (01 §3, 02 §3.5-3.6).

    Profiles come from the participants' profile sources, scaled as the file says
    and converted to kWh per step. Values above the market's largest quantity are
    clipped; every change is listed in ``warnings``.

    Args:
        resolved: The file with defaults filled (``resolve``).
        day: ``YYYY-MM-DD``; the start of the time window when ``None``.
        seed: Seed of the day's randomness; the file's day seed when ``None``.

    Raises:
        ValueError: No network, no participants, or a profile that cannot be built.
    """
    source = resolved.grid.source
    if source is None or not source.type or not source.code:
        raise ValueError("The file has no network (grid.source)")
    if not resolved.participants:
        raise ValueError("The file has no participants")
    ref = contract.NetworkRef(source.type, source.code)
    resolution, step_hours = RESOLUTIONS[
        resolved.time.resolution or "hourly_aggregated"
    ]
    steps = round(24 / step_hours)
    day = day or window_start(resolved)
    m = resolved.market
    market = MarketSpec(
        min_price=float(m.price.min),
        max_price=float(m.price.max),
        min_quantity=float(m.quantity.min),
        max_quantity=float(m.quantity.max),
        mechanism=m.mechanism,
        ledger_difficulty=int(m.ledger.difficulty) if m.ledger.enabled else 1,
        partner_preference=bool(m.partner_preference),
        async_orders=bool(m.async_orders),
        match_threshold=float(m.match_threshold),
    )
    warnings: list[str] = []
    agents = []
    for p in resolved.participants:
        _, power = participant_power(ref, p, day, 1, resolution, step_hours)
        series = {}
        for name in ("generation", "demand"):
            kwh = [max(0.0, kw * step_hours) for kw in power.get(name, [0.0] * steps)]
            if len(kwh) != steps:
                raise ValueError(
                    f"{p.id}: {name} profile has {len(kwh)} values for {steps} steps"
                )
            if max(kwh) > market.max_quantity:
                warnings.append(
                    f"{p.id}: {name} peak {max(kwh):.1f} kWh exceeds the market's "
                    f"largest quantity {market.max_quantity:g} and was clipped"
                )
                kwh = [min(v, market.max_quantity) for v in kwh]
            series[name] = tuple(kwh)
        battery = None
        b = p.battery
        if b is not None and b.nominal_capacity_kwh:
            initial = b.initial_soc
            if initial == "random":
                warnings.append(f"{p.id}: initial_soc random starts mid-range")
                initial = None
            battery = BatterySpec(
                capacity_kwh=float(b.nominal_capacity_kwh),
                min_soc=float(b.min_soc if b.min_soc is not None else 0.0),
                max_soc=float(b.max_soc if b.max_soc is not None else 1.0),
                charge_efficiency=float(b.charge_efficiency or 1.0),
                discharge_efficiency=float(b.discharge_efficiency or 1.0),
                initial_soc=None if initial is None else float(initial),
                max_power_kw=None if b.max_power_kw is None else float(b.max_power_kw),
            )
        peak = max(max(series["generation"]), max(series["demand"]), 1.0)
        agents.append(
            AgentSpec(
                id=p.id,
                bus=p.bus or "",
                capacity_kwh=min(peak, market.max_quantity),
                generation_kwh=series["generation"],
                demand_kwh=series["demand"],
                battery=battery,
            )
        )
    t = resolved.dso.tariffs
    tariffs = TariffSpec(
        source=t.source or "synthetic",
        feed_in_path=t.feed_in.path if t.feed_in else None,
        utility_path=t.utility.path if t.utility else None,
    )
    if tariffs.source == "csv" and not (tariffs.feed_in_path and tariffs.utility_path):
        warnings.append("dso.tariffs: csv without file paths, synthetic tariffs used")
        tariffs = TariffSpec(source="synthetic")
    fees = {
        n: float(getattr(resolved.dso.fees, n))
        for n in _FEE_NAMES
        if getattr(resolved.dso.fees, n, None) is not None
    }
    return EngineSpec(
        agents=tuple(agents),
        market=market,
        tariffs=tariffs,
        steps=steps,
        step_hours=step_hours,
        seed=seed if seed is not None else int(resolved.time.days.seed or 0),
        day=day,
        fees=fees,
        warnings=tuple(warnings),
    )


def build_env(env_config: dict[str, Any], grid: Any = None) -> "MarketEngine":
    """Build the market engine of one day from an ``env_config``.

    Steps (03 §4): take the resolved file and the day; build profiles through the
    participants' profile sources (01 §3); build agents with batteries, DSO tariffs
    and fees, and the market rules; hand them to the engine.

    Args:
        env_config: As made by :func:`build_env_config`.
        grid: A grid view for matching distances and fees (see ``build_grid``).
    """
    from src_thesis.marlem.environment.build import build_engine

    resolved = ExperimentFile.model_validate(env_config[ENV_CONFIG_KEY])
    cell = RunCell.model_validate(env_config["cell"])
    resolved = resolve_run(resolved, cell)
    spec = build_engine_spec(
        resolved, env_config.get("day"), env_config["episode_seed"]
    )
    return build_engine(spec, grid)


def build_grid(resolved: ExperimentFile) -> "GridModel":
    """The step-time ``GridModel`` for ``grid.source`` (01 §5); one per env."""
    raise NotImplementedError("SimBenchGrid is implemented in phase R4")
