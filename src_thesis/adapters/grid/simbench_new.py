"""pandapower adapter for every network source (02-simbench-grid.md §1–§2).

This module and the profile adapter are the only places that import
``pandapower`` and ``simbench``. Everything it returns is plain contract data
from ``marketplace/grid/contract_new.py``; no pandapower object leaves it.

Implemented (phase P3, catalog part): list networks, load them once per process,
summarise them, build a topology view, list their elements, and run one power
flow on the unmodified network for a chosen day and hour. The step-time
``GridModel`` (``SimBenchGrid``) is still a stub for phase P4.

Heavy imports happen inside the functions, so importing this module is cheap.
"""

from __future__ import annotations

import json
import math
from datetime import date
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Sequence

from src_thesis.marketplace.grid.contract_new import (
    BranchView,
    BusView,
    ElementRecord,
    GridAssessment,
    GridViolation,
    NetworkInfo,
    NetworkRef,
    NetworkSummary,
    ParticipantInjection,
    TopologyView,
)

if TYPE_CHECKING:
    import pandapower as pp

# Rows per hour in SimBench profiles (15-minute resolution) and the profile year.
ROWS_PER_HOUR = 4
SIMBENCH_YEAR = 2016

# Line ratings at or above this value are placeholders (e.g. case33bw uses 99999 kA).
PLACEHOLDER_MAX_I_KA = 9999.0
DEFAULT_V_LIMITS = (0.95, 1.05)

# SimBench network families that are far larger than a local energy market needs.
EXCLUDED_SIMBENCH_LEVELS = {"complete_data", "EHVHVMVLV"}

SIMBENCH_TYPES = {
    "rural": "rural",
    "semiurb": "semi-urban",
    "urban": "urban",
    "comm": "commercial",
    "mixed": "mixed",
}

# pandapower.networks function -> (label, voltage level)
BUILTIN_NETWORKS = {
    "case33bw": ("IEEE 33-bus (Baran & Wu)", "MV"),
    "create_cigre_network_mv": ("CIGRE MV benchmark", "MV"),
    "create_cigre_network_lv": ("CIGRE LV benchmark", "LV"),
    "mv_oberrhein": ("MV Oberrhein", "MV"),
    "create_kerber_landnetz_kabel_1": ("Kerber rural cable 1", "LV"),
    "create_kerber_vorstadtnetz_kabel_1": ("Kerber suburban cable 1", "LV"),
}


# --------------------------------------------------------------------- catalog
def simbench_label(code: str) -> tuple[str, str]:
    """``(label, voltage level)`` from a SimBench code, e.g. ``1-LV-semiurb4--0-sw``."""
    parts = code.split("-")
    level, kind, lv_part, scenario, switches = (
        parts[1],
        parts[2],
        parts[3],
        parts[4],
        parts[5],
    )
    base = kind.rstrip("0123456789")
    number = kind[len(base) :]
    name = SIMBENCH_TYPES.get(base, base) + (f" {number}" if number else "")
    if lv_part and lv_part != "all":
        name += f", LV {lv_part}"
    elif lv_part == "all":
        name += ", all LV"
    sw = "with switches" if switches == "sw" else "no switches"
    return f"{level} {name} · scenario {scenario} · {sw}", level


# Catalog order: the levels a local energy market lives on come first.
LEVEL_ORDER = ["LV", "MV", "MVLV", "HV", "HVMV", "EHV", "EHVHV"]


@lru_cache(maxsize=1)
def _simbench_codes() -> tuple[str, ...]:
    import simbench as sb

    codes = [
        c
        for c in sb.collect_all_simbench_codes()
        if c.split("-")[1] not in EXCLUDED_SIMBENCH_LEVELS
    ]
    rank = {lvl: i for i, lvl in enumerate(LEVEL_ORDER)}
    return tuple(sorted(codes, key=lambda c: rank.get(c.split("-")[1], len(rank))))


def list_networks(
    source_type: str | None = None, level: str | None = None
) -> list[NetworkInfo]:
    """Catalog entries. Counts are filled only for networks already loaded."""
    refs: list[tuple[NetworkRef, str, str]] = []
    if source_type in (None, "simbench"):
        for code in _simbench_codes():
            label, lvl = simbench_label(code)
            refs.append((NetworkRef("simbench", code), label, lvl))
    if source_type in (None, "pandapower_builtin"):
        for name, (label, lvl) in BUILTIN_NETWORKS.items():
            refs.append((NetworkRef("pandapower_builtin", name), label, lvl))
    out = []
    for ref, label, lvl in refs:
        if level and lvl != level:
            continue
        loaded = ref in _LOADED
        out.append(_info(ref, label, lvl) if loaded else NetworkInfo(ref, label, lvl))
    return out


def voltage_levels(source_type: str) -> list[str]:
    """Distinct voltage levels offered for one source type, in catalog order."""
    seen: dict[str, None] = {}
    for n in list_networks(source_type):
        seen.setdefault(n.voltage_level, None)
    return list(seen)


# --------------------------------------------------------------------- loading
_LOADED: set[NetworkRef] = set()


@lru_cache(maxsize=8)
def _load(ref: NetworkRef) -> "pp.pandapowerNet":
    """Load a network once per process. The result is a shared, read-only source."""
    import pandapower as pp

    if ref.source_type == "simbench":
        import simbench as sb

        net = sb.get_simbench_net(ref.code)
    elif ref.source_type == "pandapower_builtin":
        import pandapower.networks as pn

        if ref.code not in BUILTIN_NETWORKS:
            raise ValueError(f"Unknown pandapower built-in network {ref.code!r}")
        net = getattr(pn, ref.code)()
    elif ref.source_type == "pandapower_file":
        net = pp.from_json(ref.code)
    else:
        raise ValueError(f"Unknown network source {ref.source_type!r}")
    _LOADED.add(ref)
    return net


def _working_copy(ref: NetworkRef) -> "pp.pandapowerNet":
    import copy

    return copy.deepcopy(_load(ref))


def _label(ref: NetworkRef) -> tuple[str, str]:
    if ref.source_type == "simbench":
        return simbench_label(ref.code)
    if ref.source_type == "pandapower_builtin":
        return BUILTIN_NETWORKS.get(ref.code, (ref.code, "?"))
    return ref.code, "?"


def _has_profiles(net: Any) -> bool:
    profiles = getattr(net, "profiles", None) or {}
    return any(len(df.columns) > 1 for df in profiles.values())


def _has_line_ratings(net: Any) -> bool:
    if not len(net.line):
        return False
    rated = net.line.max_i_ka.notna() & (net.line.max_i_ka < PLACEHOLDER_MAX_I_KA)
    return bool(rated.all())


def _has_geodata(net: Any) -> bool:
    return "geo" in net.bus and bool(net.bus.geo.notna().all())


def _info(ref: NetworkRef, label: str | None = None, level: str | None = None):
    net = _load(ref)
    if label is None or level is None:
        label, level = _label(ref)
    return NetworkInfo(
        ref=ref,
        label=label,
        voltage_level=level,
        buses=len(net.bus),
        loads=len(net.load),
        sgens=len(net.sgen),
        storage=len(net.storage),
        has_profiles=_has_profiles(net),
        has_line_ratings=_has_line_ratings(net),
        has_geodata=_has_geodata(net),
    )


def summary(ref: NetworkRef) -> NetworkSummary:
    net = _load(ref)
    return NetworkSummary(
        info=_info(ref),
        total_load_kw=round(float(net.load.p_mw.sum()) * 1000, 1),
        total_generation_kw=round(float(net.sgen.p_mw.sum()) * 1000, 1),
        lines=len(net.line),
        transformers=len(net.trafo),
        profile_year=SIMBENCH_YEAR if _has_profiles(net) else None,
    )


# --------------------------------------------------------------------- topology
def _bus_ids(net: Any) -> dict[int, str]:
    """Stable string IDs: the bus name when names are unique, else ``bus <index>``."""
    names = net.bus["name"]
    if names.notna().all() and names.is_unique:
        return {int(i): str(n) for i, n in names.items()}
    return {int(i): f"bus {i}" for i in net.bus.index}


def _coordinates(net: Any) -> tuple[dict[int, tuple[float, float]], str]:
    if _has_geodata(net):
        coords = {}
        for i, geo in net.bus.geo.items():
            x, y = json.loads(geo)["coordinates"][:2]
            coords[int(i)] = (float(x), float(y))
        return coords, "geodata"
    return _radial_layout(net), "generated"


def _radial_layout(net: Any) -> dict[int, tuple[float, float]]:
    """Tree layout from the external grid: x = depth, y = spread of the leaves."""
    import networkx as nx
    import pandapower.topology as top

    graph = top.create_nxgraph(net, respect_switches=True)
    roots = [int(b) for b in net.ext_grid.bus] or [int(net.bus.index[0])]
    coords: dict[int, tuple[float, float]] = {}
    next_y = 0.0
    for component in nx.connected_components(graph):
        root = next((r for r in roots if r in component), min(component))
        tree = nx.bfs_tree(graph.subgraph(component), root)

        def place(node: int, depth: int) -> float:
            nonlocal next_y
            children = list(tree.successors(node))
            if not children:
                y = next_y
                next_y += 1.0
            else:
                y = sum(place(c, depth + 1) for c in children) / len(children)
            coords[int(node)] = (float(depth), y)
            return y

        place(root, 0)
        next_y += 2.0
    for b in net.bus.index:  # isolated buses
        coords.setdefault(int(b), (0.0, next_y))
    return coords


def _bus_kinds(net: Any) -> dict[int, str]:
    kinds: dict[int, set[str]] = {int(b): set() for b in net.bus.index}
    for b in net.load.bus:
        kinds[int(b)].add("load")
    for _, row in net.sgen.iterrows():
        kinds[int(row.bus)].add(
            "pv" if str(row.get("type", "")).upper() == "PV" else "gen"
        )
    for b in net.storage.bus:
        kinds[int(b)].add("storage")
    ext = {int(b) for b in net.ext_grid.bus}
    order = ["load", "pv", "gen", "storage"]
    return {
        b: (
            "external_grid"
            if b in ext
            else ("+".join(k for k in order if k in s) or "bus")
        )
        for b, s in kinds.items()
    }


def topology_view(ref: NetworkRef) -> TopologyView:
    net = _load(ref)
    ids = _bus_ids(net)
    coords, how = _coordinates(net)
    kinds = _bus_kinds(net)
    buses = tuple(
        BusView(
            id=ids[int(b)],
            x=coords[int(b)][0],
            y=coords[int(b)][1],
            kind=kinds[int(b)],
            vn_kv=float(net.bus.vn_kv[b]),
        )
        for b in net.bus.index
    )
    open_lines = set()
    if len(net.switch):
        mask = (net.switch.et == "l") & ~net.switch.closed.astype(bool)
        open_lines = {int(e) for e in net.switch.element[mask]}
    branches = [
        BranchView(
            id=str(row["name"]) if isinstance(row["name"], str) else f"line {i}",
            from_bus=ids[int(row.from_bus)],
            to_bus=ids[int(row.to_bus)],
            kind="line",
            closed=bool(row.in_service) and int(i) not in open_lines,
        )
        for i, row in net.line.iterrows()
    ]
    branches += [
        BranchView(
            id=str(row["name"]) if isinstance(row["name"], str) else f"trafo {i}",
            from_bus=ids[int(row.hv_bus)],
            to_bus=ids[int(row.lv_bus)],
            kind="trafo",
            closed=bool(row.in_service),
        )
        for i, row in net.trafo.iterrows()
    ]
    if len(net.switch):
        for i, row in net.switch[net.switch.et == "b"].iterrows():
            branches.append(
                BranchView(
                    id=str(row["name"]) if isinstance(row["name"], str) else f"sw {i}",
                    from_bus=ids[int(row.bus)],
                    to_bus=ids[int(row.element)],
                    kind="switch",
                    closed=bool(row.closed),
                )
            )
    ext = [ids[int(b)] for b in net.ext_grid.bus]
    return TopologyView(buses, tuple(branches), ext[0] if ext else None, how)


def elements(ref: NetworkRef, bus: str | None = None) -> list[ElementRecord]:
    net = _load(ref)
    ids = _bus_ids(net)
    out = []
    for table, kind in (("load", "load"), ("sgen", "sgen"), ("storage", "storage")):
        df = net[table]
        for i, row in df.iterrows():
            name = row.get("name")
            profile = row.get("profile") if "profile" in df else ""
            rated_mw = row.p_mw if kind == "load" else row.get("sn_mva", row.p_mw)
            if rated_mw is None or (
                isinstance(rated_mw, float) and math.isnan(rated_mw)
            ):
                rated_mw = row.p_mw
            out.append(
                ElementRecord(
                    id=str(name) if isinstance(name, str) else f"{kind} {i}",
                    element_type=kind,
                    bus=ids[int(row.bus)],
                    profile_type=str(profile) if isinstance(profile, str) else "",
                    rated_kw=round(float(rated_mw) * 1000, 2),
                )
            )
    return [e for e in out if bus is None or e.bus == bus]


# --------------------------------------------------------------------- power flow
@lru_cache(maxsize=8)
def _absolute_profiles(ref: NetworkRef) -> dict[tuple[str, str], Any]:
    import simbench as sb

    return sb.get_absolute_values(_load(ref), profiles_instead_of_study_cases=True)


def profile_rows(day: str, hour: int) -> range:
    """Rows of the 15-minute profile table for one hour of one day.

    Hourly rule of 02-simbench-grid.md §4: four rows per hour, averaged.
    """
    d = date.fromisoformat(day)
    if d.year != SIMBENCH_YEAR:
        raise ValueError(f"SimBench profiles cover {SIMBENCH_YEAR}; got {day}")
    if not 0 <= hour <= 23:
        raise ValueError(f"hour must be 0..23, got {hour}")
    start = (d - date(SIMBENCH_YEAR, 1, 1)).days * 24 * ROWS_PER_HOUR
    start += hour * ROWS_PER_HOUR
    return range(start, start + ROWS_PER_HOUR)


def preview_powerflow(ref: NetworkRef, day: str, hour: int) -> GridAssessment:
    """One power flow on a copy of the unmodified network at ``day`` / ``hour``.

    SimBench networks use their own profiles (hourly mean of four 15-minute rows).
    Networks without profiles run with their static element values.
    """
    import pandapower as pp

    net = _working_copy(ref)
    notes: list[str] = []
    if _has_profiles(net):
        rows = list(profile_rows(day, hour))
        for (table, column), df in _absolute_profiles(ref).items():
            if table not in ("load", "sgen", "storage") or df.empty:
                continue
            values = df.iloc[rows].mean()
            net[table].loc[values.index, column] = values.values
        notes.append(f"Profiles: {day}, hour {hour} (mean of 4 × 15 min).")
    else:
        notes.append("No profiles in this network: static element values.")
    if not _has_line_ratings(net):
        notes.append("No line ratings: line loading is not checked.")

    ids = _bus_ids(net)
    try:
        pp.runpp(net)
    except pp.LoadflowNotConverged:
        violation = GridViolation("NOT_CONVERGED", "network", None, None, None)
        return GridAssessment(
            hour,
            False,
            None,
            None,
            None,
            None,
            None,
            None,
            {},
            (violation,),
            tuple(notes),
        )

    vm = net.res_bus.vm_pu
    lo = net.bus.get("min_vm_pu", None)
    hi = net.bus.get("max_vm_pu", None)
    violations = []
    for b, v in vm.items():
        v_min = float(lo[b]) if lo is not None and not math.isnan(lo[b]) else None
        v_max = float(hi[b]) if hi is not None and not math.isnan(hi[b]) else None
        v_min = DEFAULT_V_LIMITS[0] if v_min is None else v_min
        v_max = DEFAULT_V_LIMITS[1] if v_max is None else v_max
        if v < v_min:
            violations.append(
                GridViolation("V_LOW", "bus", ids[int(b)], float(v), v_min)
            )
        elif v > v_max:
            violations.append(
                GridViolation("V_HIGH", "bus", ids[int(b)], float(v), v_max)
            )

    max_line = None
    if _has_line_ratings(net) and len(net.res_line):
        loading = net.res_line.loading_percent
        max_line = round(float(loading.max()), 2)
        limits = net.line.get("max_loading_percent")
        for i, value in loading.items():
            limit = 100.0
            if limits is not None and not math.isnan(limits[i]):
                limit = float(limits[i])
            if value > limit:
                violations.append(
                    GridViolation("LINE_OVERLOAD", "line", str(i), float(value), limit)
                )
    max_trafo = None
    if len(net.res_trafo):
        max_trafo = round(float(net.res_trafo.loading_percent.max()), 2)
        for i, value in net.res_trafo.loading_percent.items():
            if value > 100.0:
                violations.append(
                    GridViolation(
                        "TRAFO_OVERLOAD", "trafo", str(i), float(value), 100.0
                    )
                )

    losses_kw = 1000 * (
        float(net.res_line.pl_mw.sum()) + float(net.res_trafo.pl_mw.sum())
    )
    return GridAssessment(
        step=hour,
        converged=True,
        min_voltage_pu=round(float(vm.min()), 4),
        max_voltage_pu=round(float(vm.max()), 4),
        max_line_loading_percent=max_line,
        max_trafo_loading_percent=max_trafo,
        losses_kwh=round(losses_kw, 3),  # one hour at constant power
        external_grid_kwh=round(1000 * float(net.res_ext_grid.p_mw.sum()), 3),
        bus_voltage_pu={ids[int(b)]: round(float(v), 4) for b, v in vm.items()},
        violations=tuple(violations),
        notes=tuple(notes),
    )


# --------------------------------------------------------------------- step-time model
class SimBenchGrid:
    """Step-time ``GridModel`` for the environment (phase P4). Not implemented yet."""

    def __init__(self, grid_spec: Any) -> None:
        raise NotImplementedError

    def reset(self, episode_seed: int | None = None, day: str | None = None) -> None:
        raise NotImplementedError

    def assess(
        self, step: int, injections: Sequence[ParticipantInjection]
    ) -> GridAssessment:
        raise NotImplementedError

    def electrical_distance(self, bus_a: str, bus_b: str) -> float:
        raise NotImplementedError

    def summary(self) -> NetworkSummary:
        raise NotImplementedError

    def topology_view(self) -> TopologyView:
        raise NotImplementedError
