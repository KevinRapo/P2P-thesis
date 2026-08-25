"""Small, standalone SimBench -> pandapower AC power-flow demonstration.

This is deliberately not a MARLEM adapter.  It proves the physical-grid path
first: load a real benchmark feeder, change one connection point, solve the
entire feeder, and inspect voltage/loading/loss results.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any

import pandapower as pp
import simbench


# A small low-voltage rural feeder.  It is only a starting point; selecting the
# thesis feeder and the persistent MARLEM-agent mapping comes in the next step.
DEFAULT_SIMBENCH_CODE = "1-LV-rural1--0-sw"


@dataclass(frozen=True)
class GridResult:
    """The small result surface a future MARLEM adapter should return."""

    scenario: str
    converged: bool
    selected_load_id: int
    selected_bus_id: int
    selected_load_kw: float
    added_pv_kw: float
    min_voltage_pu: float
    max_voltage_pu: float
    max_line_loading_percent: float
    max_transformer_loading_percent: float
    line_losses_kw: float
    transformer_losses_kw: float
    total_losses_kw: float
    external_grid_p_kw: float


def _first_active_load(net: Any) -> int:
    """Choose one existing active load deterministically for this prototype."""

    active = net.load.index[net.load.in_service.astype(bool)]
    if active.empty:
        raise ValueError("The selected SimBench network has no active load element.")
    return int(active[0])


def _finite_max(table: Any, column: str) -> float:
    if table.empty or column not in table:
        return 0.0
    values = [float(value) for value in table[column].dropna()]
    return max(values, default=0.0)


def _sum_column(table: Any, column: str) -> float:
    if table.empty or column not in table:
        return 0.0
    return float(table[column].fillna(0.0).sum())


def solve_scenario(
    net: Any,
    *,
    scenario: str,
    selected_load_id: int,
    load_scale: float = 1.0,
    added_pv_kw: float = 0.0,
) -> GridResult:
    """Run one AC power flow after a controlled modification at one load bus.

    The prototype changes active and reactive load together when scaling the
    load, preserving the benchmark load's original power factor.  Added PV is a
    unity-power-factor ``sgen``.  All powers presented to this function are kW;
    pandapower tables use MW internally.
    """

    if load_scale <= 0:
        raise ValueError("load_scale must be positive.")
    if added_pv_kw < 0:
        raise ValueError("added_pv_kw must be non-negative.")

    scenario_net = deepcopy(net)
    selected_bus_id = int(scenario_net.load.at[selected_load_id, "bus"])
    scenario_net.load.at[selected_load_id, "p_mw"] *= load_scale
    scenario_net.load.at[selected_load_id, "q_mvar"] *= load_scale

    if added_pv_kw:
        pp.create_sgen(
            scenario_net,
            bus=selected_bus_id,
            p_mw=added_pv_kw / 1_000.0,
            q_mvar=0.0,
            name="prototype_pv",
        )

    pp.runpp(scenario_net, algorithm="nr")
    if not scenario_net.converged:
        raise RuntimeError(f"Power flow did not converge for scenario {scenario!r}.")

    voltages = [float(value) for value in scenario_net.res_bus.vm_pu.dropna()]
    if not voltages:
        raise RuntimeError("Power flow converged but returned no bus voltages.")

    result = GridResult(
        scenario=scenario,
        converged=bool(scenario_net.converged),
        selected_load_id=selected_load_id,
        selected_bus_id=selected_bus_id,
        selected_load_kw=float(scenario_net.load.at[selected_load_id, "p_mw"] * 1_000.0),
        added_pv_kw=added_pv_kw,
        min_voltage_pu=min(voltages),
        max_voltage_pu=max(voltages),
        max_line_loading_percent=_finite_max(scenario_net.res_line, "loading_percent"),
        max_transformer_loading_percent=_finite_max(
            scenario_net.res_trafo, "loading_percent"
        ),
        line_losses_kw=_sum_column(scenario_net.res_line, "pl_mw") * 1_000.0,
        transformer_losses_kw=_sum_column(scenario_net.res_trafo, "pl_mw") * 1_000.0,
        total_losses_kw=(
            _sum_column(scenario_net.res_line, "pl_mw")
            + _sum_column(scenario_net.res_trafo, "pl_mw")
        )
        * 1_000.0,
        # Positive normally means import from the upstream grid in this setup.
        external_grid_p_kw=_sum_column(scenario_net.res_ext_grid, "p_mw") * 1_000.0,
    )
    if not all(isfinite(value) for value in asdict(result).values() if isinstance(value, float)):
        raise RuntimeError(f"Scenario {scenario!r} returned a non-finite grid result.")
    return result


def run_demo(
    simbench_code: str = DEFAULT_SIMBENCH_CODE,
    *,
    heavy_load_scale: float = 2.0,
    pv_kw: float = 5.0,
) -> list[GridResult]:
    """Load a SimBench feeder and solve base, heavy-load, and PV cases."""

    if heavy_load_scale <= 1:
        raise ValueError("heavy_load_scale must be greater than one.")
    net = simbench.get_simbench_net(simbench_code)
    selected_load_id = _first_active_load(net)
    return [
        solve_scenario(net, scenario="base", selected_load_id=selected_load_id),
        solve_scenario(
            net,
            scenario="double_selected_load",
            selected_load_id=selected_load_id,
            load_scale=heavy_load_scale,
        ),
        solve_scenario(
            net,
            scenario="add_pv_at_selected_bus",
            selected_load_id=selected_load_id,
            added_pv_kw=pv_kw,
        ),
    ]
