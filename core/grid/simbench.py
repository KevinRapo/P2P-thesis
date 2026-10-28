"""pandapower adapter for SimBench and the pandapower built-in networks.

The only module that imports ``pandapower`` and ``simbench``. Everything it
returns is plain contract data from ``core/grid/contract.py``; no pandapower object
leaves it.

It lists networks, loads them once per process (with a disk cache), summarises
them, builds a topology view, lists their elements and profiles, and runs one
power flow on the unmodified network for a chosen day and hour. The step-time
power flow is ``core/grid/powerflow.py``.

Heavy imports happen inside the functions, so importing this module is cheap.
"""

from __future__ import annotations

import json
import math
import os
import pickle
import shutil
import threading
from dataclasses import replace
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Sequence

from core.grid.contract import (
    BranchView,
    BusView,
    ElementRecord,
    GridAssessment,
    GridLimits,
    GridViolation,
    NetworkInfo,
    NetworkRef,
    NetworkSummary,
    ProfileRecord,
    TopologyView,
)

if TYPE_CHECKING:
    import pandapower as pp

# --------------------------------------------------------------------------------------
# Settings: profile layout, limits, network names
# --------------------------------------------------------------------------------------
# Rows per hour in SimBench profiles (15-minute resolution) and the profile year.
ROWS_PER_HOUR = 4
SIMBENCH_YEAR = 2016

# Line ratings at or above this value are placeholders (e.g. case33bw uses 99999 kA).
PLACEHOLDER_MAX_I_KA = 9999.0
DEFAULT_V_LIMITS = (0.95, 1.05)
BACKGROUNDS = ("mapped_replacement", "scaled_background", "no_background")

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


# --------------------------------------------------------------------------------------
# Catalog: which networks exist and their names
# --------------------------------------------------------------------------------------
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


def simbench_facets(code: str) -> tuple[str, int, bool]:
    """``(category, scenario, switches)`` of a SimBench code, e.g. ``("semi-urban",
    0, True)`` for ``1-LV-semiurb4--0-sw``."""
    parts = code.split("-")
    base = parts[2].rstrip("0123456789")

    return SIMBENCH_TYPES.get(base, base), int(parts[4]), parts[5] == "sw"


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
        info = _info(ref, label, lvl) if loaded else NetworkInfo(ref, label, lvl)

        if ref.source_type == "simbench":
            category, scenario, switches = simbench_facets(ref.code)
            info = replace(
                info, category=category, scenario=scenario, switches=switches
            )

        out.append(info)

    return out


def voltage_levels(source_type: str) -> list[str]:
    """Distinct voltage levels offered for one source type, in catalog order."""
    seen: dict[str, None] = {}

    for n in list_networks(source_type):
        seen.setdefault(n.voltage_level, None)

    return list(seen)


# --------------------------------------------------------------------------------------
# Loading and the disk cache
# --------------------------------------------------------------------------------------
# Networks are cached twice. In RAM, the last ``RAM_NETWORKS`` loaded networks
# (``_load``). On disk, every SimBench and built-in network once built, as a pickle
# in the folder given to ``use_cache``: building one from SimBench's CSV files takes
# 3-4 s, reading the pickle back 0.03-0.08 s. The folder name holds the pandapower
# and SimBench versions, so an upgrade starts a fresh cache.
_LOADED: set[NetworkRef] = set()
RAM_NETWORKS = 16
_CACHE_DIR: Path | None = None
_CACHE_LOCK = threading.Lock()


def use_cache(folder: Path | None) -> None:
    """Keep built networks as files in ``folder`` (``None``: RAM only)."""
    global _CACHE_DIR
    _CACHE_DIR = Path(folder) if folder else None


def _cache_path(ref: NetworkRef) -> Path | None:
    """The cache file of a network; ``None`` without a cache or for user files."""
    if _CACHE_DIR is None or ref.source_type == "pandapower_file":
        return None

    import pandapower as pp
    import simbench as sb

    version = f"pandapower-{pp.__version__}_simbench-{sb.__version__}"

    return _CACHE_DIR / version / ref.source_type / f"{ref.code}.pkl"


def _read_or_build(ref: NetworkRef) -> "pp.pandapowerNet":
    """The network from its cache file, or built and then written to the cache."""
    path = _cache_path(ref)

    if path is not None and path.exists():
        try:
            with path.open("rb") as f:
                return pickle.load(f)
        except Exception:  # noqa: BLE001  a damaged file is rebuilt
            path.unlink(missing_ok=True)

    net = _build(ref)

    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")

        with tmp.open("wb") as f:
            pickle.dump(net, f, protocol=pickle.HIGHEST_PROTOCOL)

        with _CACHE_LOCK:
            os.replace(tmp, path)

    return net


def cache_status() -> tuple[str, int, int]:
    """(cache folder, networks cached, bytes); ``("", 0, 0)`` without a cache."""
    if _CACHE_DIR is None:
        return "", 0, 0

    files = list(_CACHE_DIR.rglob("*.pkl")) if _CACHE_DIR.exists() else []

    return str(_CACHE_DIR), len(files), sum(f.stat().st_size for f in files)


def cache_coverage() -> dict[str, tuple[int, int]]:
    """How much of the catalogue is cached: ``{group: (cached, total)}``.

    One group per SimBench voltage level, in catalog order, and ``"built-in"`` for
    the pandapower networks. Only files of the current pandapower and SimBench
    versions count. Empty without a cache.
    """
    if _CACHE_DIR is None:
        return {}

    groups: dict[str, list[NetworkRef]] = {}

    for code in _simbench_codes():
        groups.setdefault(simbench_label(code)[1], []).append(
            NetworkRef("simbench", code)
        )

    groups["built-in"] = [NetworkRef("pandapower_builtin", n) for n in BUILTIN_NETWORKS]
    folder = _cache_path(NetworkRef("simbench", "x")).parents[1]
    cached = (
        {(p.parent.name, p.stem) for p in folder.rglob("*.pkl")}
        if folder.exists()
        else set()
    )

    return {
        group: (sum((r.source_type, r.code) in cached for r in refs), len(refs))
        for group, refs in groups.items()
    }


def is_cached(ref: NetworkRef) -> bool:
    """Whether a network is in RAM or in the disk cache (opens at once)."""
    path = _cache_path(ref)
    return ref in _LOADED or (path is not None and path.exists())


def warm_cache(
    levels: Sequence[str], progress: Callable[[int, int], None] | None = None
) -> int:
    """Build the cache files of every SimBench network of ``levels`` not yet cached.

    The networks are not kept in RAM. Safe to run in a background thread.

    Args:
        levels: Voltage levels, e.g. ``["LV", "MV"]``.
        progress: Called with (done, total) after each network.

    Returns:
        The number of networks built.
    """
    if _CACHE_DIR is None:
        return 0

    refs = [
        NetworkRef("simbench", c)
        for c in _simbench_codes()
        if simbench_label(c)[1] in set(levels)
    ]
    todo = [r for r in refs if not is_cached(r)]

    for i, ref in enumerate(todo, start=1):
        _read_or_build(ref)
        if progress:
            progress(i, len(todo))

    return len(todo)


def clear_cache() -> None:
    """Delete every cache file (networks are built again when opened)."""
    if _CACHE_DIR is not None and _CACHE_DIR.exists():
        shutil.rmtree(_CACHE_DIR, ignore_errors=True)


# Networks given directly (``provide``): used instead of loading the reference.
_PROVIDED: dict[NetworkRef, Any] = {}


def provide(ref: NetworkRef, net: "pp.pandapowerNet | None") -> None:
    """Use ``net`` for ``ref`` instead of loading it (``None``: load it again).

    The seam for tests and for networks built in memory: a small hand-made
    pandapower net registered under any reference works with every function of
    this module, and with the services above it, without SimBench.
    """
    for cached in (_load_cached, _absolute_profiles):
        cached.cache_clear()
    if net is None:
        _PROVIDED.pop(ref, None)
        _LOADED.discard(ref)
    else:
        _PROVIDED[ref] = net
        _LOADED.add(ref)


def _load(ref: NetworkRef) -> "pp.pandapowerNet":
    """The network of ``ref``: provided, or loaded once per process (from the disk
    cache if it has it). The result is a shared, read-only source.
    """
    if ref in _PROVIDED:
        return _PROVIDED[ref]
    return _load_cached(ref)


@lru_cache(maxsize=RAM_NETWORKS)
def _load_cached(ref: NetworkRef) -> "pp.pandapowerNet":
    net = _read_or_build(ref)
    _LOADED.add(ref)
    return net


def _build(ref: NetworkRef) -> "pp.pandapowerNet":
    """Build a network from its source (SimBench CSVs, pandapower, a file)."""
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

    return net


def _working_copy(ref: NetworkRef) -> "pp.pandapowerNet":
    import copy

    return copy.deepcopy(_load(ref))


# --------------------------------------------------------------------------------------
# Network facts: summary and flags
# --------------------------------------------------------------------------------------
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
    """Totals and element counts of one network.

    The network is loaded once per process and cached.

    Args:
        ref: The network.
    """
    net = _load(ref)
    return NetworkSummary(
        info=_info(ref),
        total_load_kw=round(float(net.load.p_mw.sum()) * 1000, 1),
        total_generation_kw=round(float(net.sgen.p_mw.sum()) * 1000, 1),
        lines=len(net.line),
        transformers=len(net.trafo),
        profile_year=SIMBENCH_YEAR if _has_profiles(net) else None,
    )


# --------------------------------------------------------------------------------------
# Topology: buses and branches for plotting
# --------------------------------------------------------------------------------------
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
        return _pull_upstream_buses(net, coords), "geodata"
    return _radial_layout(net), "generated"


def _pull_upstream_buses(
    net: Any, coords: dict[int, tuple[float, float]]
) -> dict[int, tuple[float, float]]:
    """Draw upstream buses (reached only through transformers) at their transformer.

    In SimBench networks the bus behind the transformer, e.g. the 20 kV bus that
    feeds an LV network and holds the external grid, keeps its real position in
    the upstream network, often hundreds of metres from the substation. Drawn
    there it lands among unrelated buses with a long transformer line. Such a
    bus is placed just above the transformer's other side instead.
    """
    on_lines = set(net.line.from_bus) | set(net.line.to_bus)
    partners: dict[int, list[int]] = {}

    for _, row in net.trafo.iterrows():
        hv, lv = int(row.hv_bus), int(row.lv_bus)
        partners.setdefault(hv, []).append(lv)
        partners.setdefault(lv, []).append(hv)

    ys = [y for _, y in coords.values()]
    offset = 0.04 * ((max(ys) - min(ys)) or 1.0)
    out = dict(coords)

    for bus, others in partners.items():
        if bus in on_lines or not others:
            continue

        others = [o for o in others if o in coords]

        if not others:
            continue

        x = sum(coords[o][0] for o in others) / len(others)
        y = max(coords[o][1] for o in others) + offset
        out[bus] = (x, y)

    return out


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


BUS_KIND_ORDER = ("load", "pv", "gen", "storage")


def _element_kinds(net: Any) -> dict[int, str]:
    """What is connected to each bus: load, pv, gen (any other static generator)
    and storage, joined by "+" in that order; "" for a bus without elements."""
    kinds: dict[int, set[str]] = {int(b): set() for b in net.bus.index}

    for b in net.load.bus:
        kinds[int(b)].add("load")

    for _, row in net.sgen.iterrows():
        kinds[int(row.bus)].add(
            "pv" if str(row.get("type", "")).upper() == "PV" else "gen"
        )

    for b in net.storage.bus:
        kinds[int(b)].add("storage")

    return {b: "+".join(k for k in BUS_KIND_ORDER if k in s) for b, s in kinds.items()}


def _bus_kinds(net: Any) -> dict[int, str]:
    ext = {int(b) for b in net.ext_grid.bus}
    return {
        b: "external_grid" if b in ext else (kind or "bus")
        for b, kind in _element_kinds(net).items()
    }


def bus_kinds(ref: NetworkRef) -> dict[str, str]:
    """Each bus with elements and what is on it: ``"load"``, ``"load+pv"``,
    ``"load+storage"``, ``"load+gen+storage"``, ... (load, pv, gen, storage joined
    by "+" in that order; gen is any static generator other than PV). Buses
    without elements are left out.

    Args:
        ref: The network.
    """
    net = _load(ref)
    ids = _bus_ids(net)

    return {ids[b]: kind for b, kind in _element_kinds(net).items() if kind}


def topology_view(ref: NetworkRef) -> TopologyView:
    """The network's shape as plain records: buses and branches.

    Branches are lines, transformers and bus-to-bus switches. A branch that is out
    of service or behind an open switch has ``closed=False``. Networks without
    geodata get a generated radial layout (``coordinates="generated"``).

    Args:
        ref: The network.
    """
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


# --------------------------------------------------------------------------------------
# Elements: loads, generators, storage
# --------------------------------------------------------------------------------------
def elements(ref: NetworkRef, bus: str | None = None) -> list[ElementRecord]:
    """Loads, static generators and storage units of a network.

    Args:
        ref: The network.
        bus: Bus ID as in the topology view; ``None`` for all elements.
    """
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
                    energy_kwh=(
                        round(float(row.max_e_mwh) * 1000, 2)
                        if kind == "storage"
                        else 0.0
                    ),
                )
            )

    return [e for e in out if bus is None or e.bus == bus]


# --------------------------------------------------------------------------------------
# Profiles: a network's time series
# --------------------------------------------------------------------------------------
@lru_cache(maxsize=8)
def _absolute_profiles(ref: NetworkRef) -> dict[tuple[str, str], Any]:
    import simbench as sb

    return sb.get_absolute_values(_load(ref), profiles_instead_of_study_cases=True)


PROFILE_TABLES = ("load", "renewables", "powerplants", "storage")
# Which element table uses the profiles of each SimBench profile table.
PROFILE_USERS = {
    "load": "load",
    "renewables": "sgen",
    "powerplants": "sgen",
    "storage": "storage",
}
RESOLUTION_ROWS = {"15min": 1, "hourly": ROWS_PER_HOUR, "daily": 24 * ROWS_PER_HOUR}


def _profile_columns(source: Any) -> dict[tuple[str, str], dict[str, str]]:
    """(table, profile name) -> {quantity: column} for every profile.

    ``source`` is a network (its ``profiles``) or a profiles dict (the catalogue).
    """
    # A pandapower network is itself a dict, so only a plain dict is the catalogue.
    if type(source) is dict:
        profiles = source
    else:
        profiles = getattr(source, "profiles", None)

    out: dict[tuple[str, str], dict[str, str]] = {}

    for table in PROFILE_TABLES:
        df = (profiles or {}).get(table)
        if df is None:
            continue
        for column in df.columns:
            if column == "time":
                continue

            name, quantity = column, "p"

            for suffix, q in (("_pload", "p"), ("_qload", "q"), ("_pgen", "p")):
                if column.endswith(suffix):
                    name, quantity = column[: -len(suffix)], q

            out.setdefault((table, name), {})[quantity] = column

    return out


def profile_catalog(ref: NetworkRef) -> list[ProfileRecord]:
    """Every profile the network ships, with how many elements use it.

    Networks without profiles (pandapower built-ins, most files) return ``[]``.
    """
    net = _load(ref)
    counts = {}

    for table in set(PROFILE_USERS.values()):
        users = getattr(net, table)

        if "profile" in users:
            counts[table] = users["profile"].value_counts().to_dict()

    return _profile_records(getattr(net, "profiles", None) or {}, counts)


def _profile_records(
    profiles: dict[str, Any], counts: dict[str, dict[str, int]] | None = None
) -> list[ProfileRecord]:
    """The same profile descriptions for a network and the complete catalogue."""
    out = []

    for (table, name), columns in _profile_columns(profiles).items():
        values = profiles[table][columns.get("p", next(iter(columns.values())))]

        out.append(
            ProfileRecord(
                name=name,
                table=table,
                quantities=tuple(q for q in ("p", "q") if q in columns),
                elements=int((counts or {}).get(PROFILE_USERS[table], {}).get(name, 0)),
                mean=round(float(values.mean()), 4),
                peak=round(float(values.max()), 4),
            )
        )

    return sorted(out, key=lambda r: (PROFILE_TABLES.index(r.table), r.name))


def _window(start: str, days: int, resolution: str) -> tuple[date, int, int, int]:
    """(first day, first row, last row, rows per output value) of a time window."""
    d = date.fromisoformat(start)

    if d.year != SIMBENCH_YEAR:
        raise ValueError(f"SimBench profiles cover {SIMBENCH_YEAR}; got {start}")

    if resolution not in RESOLUTION_ROWS:
        raise ValueError(f"resolution must be one of {list(RESOLUTION_ROWS)}")

    year_days = (date(SIMBENCH_YEAR + 1, 1, 1) - date(SIMBENCH_YEAR, 1, 1)).days
    first = (d - date(SIMBENCH_YEAR, 1, 1)).days * 24 * ROWS_PER_HOUR
    last = min(first + days * 24 * ROWS_PER_HOUR, year_days * 24 * ROWS_PER_HOUR)

    return d, first, last, RESOLUTION_ROWS[resolution]


def _labels(d: date, count: int, step: int, resolution: str) -> list[str]:
    """Time labels counted from the row (15 min each), like ``profile_rows``.

    SimBench's own time column is local time and jumps an hour at the
    daylight-saving switch, which would shift the labels against the rows.
    """
    begin = datetime(d.year, d.month, d.day)
    fmt = "%Y-%m-%d" if resolution == "daily" else "%Y-%m-%d %H:%M"

    return [
        (begin + timedelta(minutes=15 * step * i)).strftime(fmt) for i in range(count)
    ]


def _aggregate(values: Any, step: int) -> list[float]:
    """Mean of every ``step`` rows of an already selected time window."""
    means = values.groupby([i // step for i in range(len(values))]).mean()

    return [float(v) for v in means]


def profile_series(
    ref: NetworkRef,
    names: Sequence[str],
    start: str,
    days: int,
    resolution: str = "hourly",
    quantity: str = "p",
) -> tuple[list[str], dict[str, list[float]]]:
    """Values of the given profiles over a time window, as factors of rated power.

    Args:
        ref: The network.
        names: Profile names (as in ``profile_catalog``).
        start: First day, ``YYYY-MM-DD`` in the profile year.
        days: Number of days; clipped at the end of the year.
        resolution: ``"15min"`` (raw), ``"hourly"`` or ``"daily"`` (means).
        quantity: ``"p"`` or ``"q"`` (only loads have ``q``).

    Returns:
        Time labels (standard time, counted in 15-minute rows from 1 January) and,
        per profile name, its values (factors of rated power).
    """
    return _series(_load(ref).profiles, names, start, days, resolution, quantity)


def _series(
    profiles: dict[str, Any],
    names: Sequence[str],
    start: str,
    days: int,
    resolution: str,
    quantity: str,
) -> tuple[list[str], dict[str, list[float]]]:
    """``profile_series`` of profile tables (a network's or the catalogue's)."""
    d, first, last, step = _window(start, days, resolution)
    columns = _profile_columns(profiles)
    values: dict[str, list[float]] = {}

    for table, name in columns:
        if name in names and quantity in columns[(table, name)]:
            column = profiles[table][columns[(table, name)][quantity]]
            window = column.iloc[first:last]
            values[name] = [round(v, 4) for v in _aggregate(window, step)]

    count = len(next(iter(values.values()), []))

    return _labels(d, count, step, resolution), values


def profile_power(
    ref: NetworkRef,
    names: Sequence[str],
    start: str,
    days: int,
    resolution: str = "hourly",
    quantity: str = "p",
    per_element: bool = False,
) -> tuple[list[str], dict[str, list[float]]]:
    """The profiles scaled by the rated power of the elements that use them, in kW.

    Each element's time series is its profile factor times its own rated power
    (SimBench's absolute values, ``simbench.get_absolute_values``): the power it
    draws or feeds in on the unmodified network.

    Args:
        ref: The network.
        names: Profile names (as in ``profile_catalog``).
        start: First day, ``YYYY-MM-DD`` in the profile year.
        days: Number of days; clipped at the end of the year.
        resolution: ``"15min"`` (raw), ``"hourly"`` or ``"daily"`` (means).
        quantity: ``"p"`` (kW) or ``"q"`` (kvar; loads only).
        per_element: One series per element instead of one sum per profile.

    Returns:
        Time labels and, per profile ("H0-A (6)") or per element
        ("LV4.101 Load 30 · H0-A"), its power in kW or kvar.
    """
    d, first, last, step = _window(start, days, resolution)
    net = _load(ref)
    absolute = _absolute_profiles(ref)
    column = {"p": "p_mw", "q": "q_mvar"}[quantity]
    values: dict[str, list[float]] = {}

    for table, name in _profile_columns(net):
        if name not in names:
            continue

        element_table = PROFILE_USERS[table]
        frame = absolute.get((element_table, column))
        users = getattr(net, element_table)

        if frame is None or "profile" not in users:
            continue

        ids = [i for i in users.index[users["profile"] == name] if i in frame.columns]

        if not ids:
            continue

        # Select the window before adding or scaling the full-year profiles.
        frame = frame.iloc[first:last]

        if per_element:
            for i in ids:
                kw = _aggregate(frame[i] * 1000, step)
                values[f"{users.at[i, 'name']} · {name}"] = [round(v, 3) for v in kw]
        else:
            kw = _aggregate(frame[ids].sum(axis=1) * 1000, step)
            values[f"{name} ({len(ids)})"] = [round(v, 3) for v in kw]

    count = len(next(iter(values.values()), []))

    return _labels(d, count, step, resolution), values


def element_power(
    ref: NetworkRef,
    ids: Sequence[str],
    start: str,
    days: int,
    resolution: str = "hourly",
) -> tuple[list[str], dict[str, list[float]]]:
    """Active power of individual elements over a time window, in kW.

    SimBench elements follow their profile scaled by their rated power; elements
    without a profile (pandapower built-ins) keep their static value.

    Args:
        ref: The network.
        ids: Element names, as in ``elements``.
        start: First day, ``YYYY-MM-DD`` in the profile year.
        days: Number of days; clipped at the end of the year.
        resolution: ``"15min"`` (raw), ``"hourly"`` or ``"daily"`` (means).

    Returns:
        Time labels and, per element found, its power in kW.
    """
    d, first, last, step = _window(start, days, resolution)
    net = _load(ref)
    absolute = _absolute_profiles(ref) if _has_profiles(net) else {}
    count = math.ceil((last - first) / step)
    wanted = set(ids)
    values: dict[str, list[float]] = {}

    for table in ("load", "sgen", "storage"):
        frame = absolute.get((table, "p_mw"))

        if frame is not None:
            frame = frame.iloc[first:last]

        for i, row in net[table].iterrows():
            name = row.get("name")
            element_id = str(name) if isinstance(name, str) else f"{table} {i}"

            if element_id not in wanted:
                continue

            if frame is not None and i in frame.columns:
                kw = _aggregate(frame[i] * 1000, step)
            else:
                kw = [float(row.p_mw) * 1000] * count

            values[element_id] = [round(v, 3) for v in kw]

    return _labels(d, count, step, resolution), values


# --------------------------------------------------------------------------------------
# Catalogue: every profile SimBench ships
# --------------------------------------------------------------------------------------
@lru_cache(maxsize=3)
def _catalogue(scenario: int) -> dict[str, Any]:
    """All SimBench profiles of a scenario, independent of any network (cached)."""
    import simbench as sb

    return sb.get_all_simbench_profiles(scenario)


def catalogue_profiles(scenario: int = 0) -> list[ProfileRecord]:
    """Every profile SimBench ships, not only those one network uses.

    Args:
        scenario: SimBench scenario (0 = today, 1 and 2 = future scenarios).

    Returns:
        One record per profile; ``elements`` is 0, as no network is involved.
    """
    profiles = {
        table: frame for table, frame in _catalogue(scenario).items() if not frame.empty
    }

    return _profile_records(profiles)


def catalogue_series(
    names: Sequence[str],
    start: str,
    days: int,
    resolution: str = "hourly",
    quantity: str = "p",
    scenario: int = 0,
) -> tuple[list[str], dict[str, list[float]]]:
    """Like ``profile_series``, for profiles of the complete catalogue."""
    return _series(_catalogue(scenario), names, start, days, resolution, quantity)


# --------------------------------------------------------------------------------------
# Power flow: one-hour preview and its assessment
# --------------------------------------------------------------------------------------
def profile_rows(day: str, hour: int) -> range:
    """Rows of the 15-minute profile table for one hour of one day.

    Hourly values: the four quarter-hour rows of each hour, averaged.
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

    try:
        pp.runpp(net)
    except pp.LoadflowNotConverged:
        return _not_converged(hour, notes)

    return _assessment(net, hour, 1.0, notes)


def _not_converged(step: int, notes: list[str]) -> GridAssessment:
    """The assessment of a power flow that did not converge."""
    violation = GridViolation("NOT_CONVERGED", "network", None, None, None)
    return GridAssessment(
        step, False, None, None, None, None, None, None, {}, (violation,), tuple(notes)
    )


def _assessment(
    net: Any,
    step: int,
    step_hours: float,
    notes: list[str],
    limits: "GridLimits | None" = None,
) -> GridAssessment:
    """Read a solved network: voltages, loadings, losses, violations.

    Args:
        net: The network after a converged power flow.
        step: The step the flow belongs to.
        step_hours: Hours the step lasts (power to energy).
        notes: Notes to carry into the result.
        limits: Limits that replace the network's own where set.
    """
    limits = limits or GridLimits()
    ids = _bus_ids(net)
    vm = net.res_bus.vm_pu
    lo = net.bus.get("min_vm_pu", None)
    hi = net.bus.get("max_vm_pu", None)
    violations = []

    for b, v in vm.items():
        v_min = float(lo[b]) if lo is not None and not math.isnan(lo[b]) else None
        v_max = float(hi[b]) if hi is not None and not math.isnan(hi[b]) else None
        v_min = limits.v_min_pu if limits.v_min_pu is not None else v_min
        v_max = limits.v_max_pu if limits.v_max_pu is not None else v_max
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
        line_limits = net.line.get("max_loading_percent")

        for i, value in loading.items():
            limit = limits.line_max_percent
            if limit is None:
                limit = 100.0
                if line_limits is not None and not math.isnan(line_limits[i]):
                    limit = float(line_limits[i])
            if value > limit:
                violations.append(
                    GridViolation(
                        "LINE_OVERLOAD",
                        "line",
                        _branch_name(net.line, i, "line"),
                        float(value),
                        limit,
                    )
                )

    max_trafo = None

    if len(net.res_trafo):
        max_trafo = round(float(net.res_trafo.loading_percent.max()), 2)
        for i, value in net.res_trafo.loading_percent.items():
            trafo_limit = limits.trafo_max_percent or 100.0
            if value > trafo_limit:
                violations.append(
                    GridViolation(
                        "TRAFO_OVERLOAD", "trafo", str(i), float(value), trafo_limit
                    )
                )

    losses_kw = 1000 * (
        float(net.res_line.pl_mw.sum()) + float(net.res_trafo.pl_mw.sum())
    )

    return GridAssessment(
        step=step,
        converged=True,
        min_voltage_pu=round(float(vm.min()), 4),
        max_voltage_pu=round(float(vm.max()), 4),
        max_line_loading_percent=max_line,
        max_trafo_loading_percent=max_trafo,
        losses_kwh=round(losses_kw * step_hours, 3),
        external_grid_kwh=round(
            1000 * float(net.res_ext_grid.p_mw.sum()) * step_hours, 3
        ),
        bus_voltage_pu={ids[int(b)]: round(float(v), 4) for b, v in vm.items()},
        violations=tuple(violations),
        notes=tuple(notes),
        line_loading_percent={
            _branch_name(net.line, i, "line"): round(float(v), 2)
            for i, v in net.res_line.loading_percent.items()
        },
    )


def _branch_name(table: Any, i: Any, kind: str) -> str:
    """A line's or transformer's ID, as in ``topology_view``."""
    name = table.at[i, "name"]
    return str(name) if isinstance(name, str) else f"{kind} {i}"
