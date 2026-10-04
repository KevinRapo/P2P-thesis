"""Network catalogue statistics, generated into ``guide/networks.md``.

Every network the Studio offers (SimBench and the pandapower built-ins) is
loaded through the application services, its facts and element mix are
computed, and the result is kept in ``guide/networks.json``. The document's
tables are generated from that file: a block between
``<!-- BEGIN generated:networks KEY -->`` and ``<!-- END generated:networks -->``
is replaced by the table ``KEY``.

    python docs_thesis/networks.py            # rewrite the tables from networks.json
    python docs_thesis/networks.py --collect  # reload every network first (slow)
    python docs_thesis/networks.py --check    # exit 1 if a table is stale
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

DOCS = Path(__file__).resolve().parent
ROOT = DOCS.parent
DATA = DOCS / "guide" / "networks.json"
PAGE = DOCS / "guide" / "networks.md"
BLOCK = re.compile(
    r"(<!-- BEGIN generated:networks (\w+) -->\n).*?(<!-- END generated:networks -->)",
    re.S,
)
LEVELS = ["LV", "MV", "HV", "EHV", "LVMV", "MVLV", "HVMV", "MVHV", "EHVHV", "HVEHV"]
LOAD_CLASSES = {
    "household": "Households",
    "commercial": "Commercial",
    "agricultural": "Farms",
    "special_slp": "Other SLP",
    "heat_pump": "Heat pumps",
    "ev": "EV charging",
    "hv_grid": "Omitted HV grids",
    "grid": "Aggregated grids",
    "storage": "Storage profiles",
    "other": "Other",
}
GENERATION = {
    "pv": "PV",
    "wind": "Wind",
    "biomass": "Biomass",
    "hydro": "Hydro",
    "power_plant": "Conventional",
    "exchange": "Import",
    "grid": "Aggregated grids",
    "hv_grid": "Omitted HV grids",
    "storage": "Storage profiles",
    "other": "Other",
}


# ------------------------------------------------------------------ collect
def collect() -> list[dict[str, Any]]:
    """Load every catalog network through the services and compute its facts."""
    sys.path.insert(0, str(ROOT))
    from src_thesis.application.container import build_services

    services = build_services()
    rows = []
    for source_type in ("simbench", "pandapower_builtin"):
        for info in services.grid.list_networks(source_type):
            print(info.source.code, flush=True)
            try:
                rows.append(_facts(services, info.source))
            except Exception as error:  # noqa: BLE001  report and continue
                print(f"  skipped: {error}", flush=True)
    return rows


def _facts(services: Any, source: Any) -> dict[str, Any]:
    """The facts of one network (counts, ratings, element mix by class)."""
    summary = services.grid.summary(source)
    info = summary.info
    types = {t.code: t.category for t in services.profiles.profile_types(source)}
    elements = services.grid.elements(source)
    loads = [e for e in elements if e.element_type == "load"]
    sgens = [e for e in elements if e.element_type == "sgen"]
    storage = [e for e in elements if e.element_type == "storage"]
    load_kw: Counter[str] = Counter()
    load_n: Counter[str] = Counter()
    for e in loads:
        category = types.get(e.profile_type, "other")
        load_kw[category] += e.rated_kw
        load_n[category] += 1
    gen_kw: Counter[str] = Counter()
    for e in sgens:
        gen_kw[types.get(e.profile_type, "other")] += e.rated_kw
    load_buses = {e.bus for e in loads}
    gen_buses = {e.bus for e in sgens}
    pv_buses = {e.bus for e in sgens if types.get(e.profile_type) == "pv"}
    return {
        "code": source.code,
        "type": source.type,
        **_parse(source.code),
        "label": info.label,
        "level": info.voltage_level,
        "buses": info.buses,
        "lines": summary.lines,
        "trafos": summary.transformers,
        "loads": len(loads),
        "sgens": len(sgens),
        "storage": len(storage),
        "load_kw": round(summary.total_load_kw, 1),
        "generation_kw": round(summary.total_generation_kw, 1),
        "storage_kw": round(sum(e.rated_kw for e in storage), 1),
        "load_kw_by_class": {k: round(v, 1) for k, v in load_kw.items()},
        "loads_by_class": dict(load_n),
        "generation_kw_by_class": {k: round(v, 1) for k, v in gen_kw.items()},
        "load_buses": len(load_buses),
        "prosumer_buses": len(load_buses & gen_buses),
        "pv_buses": len(pv_buses & load_buses),
        "profiles": bool(info.has_profiles),
        "line_ratings": bool(info.has_line_ratings),
        "geodata": bool(info.has_geodata),
    }


def _parse(code: str) -> dict[str, Any]:
    """Grid, scenario and switch variant of a SimBench code.

    ``1-LV-rural1--0-sw`` -> grid ``1-LV-rural1``, scenario 0, switches;
    ``1-MVLV-rural-all-1-no_sw`` -> grid ``1-MVLV-rural-all``, scenario 1.
    """
    match = re.match(r"(.+?)-{1,2}(\d)-(no_sw|sw)$", code)
    if not match:
        return {"grid": code, "scenario": None, "switches": None}
    return {
        "grid": match.group(1),
        "scenario": int(match.group(2)),
        "switches": match.group(3) == "sw",
    }


# ------------------------------------------------------------------ render
def _gen(row: dict) -> float:
    """Rated generation: the sum over the generator types (as the PV share)."""
    return sum(row["generation_kw_by_class"].values())


def _pct(part: float, whole: float) -> str:
    return f"{100 * part / whole:.0f} %" if whole else "—"


def _kw(value: float) -> str:
    if value >= 10_000:
        return f"{value / 1000:,.0f} MW"
    if value >= 1_000:
        return f"{value / 1000:,.1f} MW"
    return f"{value:,.0f} kW"


def _yes(value: bool) -> str:
    return "yes" if value else "no"


def _merge_switch_variants(rows: list[dict]) -> list[dict]:
    """One row per SimBench grid and scenario.

    The ``sw`` and ``no_sw`` variants have the same loads, generators and lines;
    the ``sw`` variant adds bus-bar buses for its switches, so ``bus_text`` shows
    both counts (``sw / no_sw``) when they differ.
    """
    ignore = {"code", "switches", "label", "buses"}
    keyed: dict[tuple, dict] = {}
    for row in rows:
        row = {**row, **_parse(row["code"])}
        if row["scenario"] is None:
            keyed[(row["code"],)] = {**row, "bus_text": str(row["buses"])}
            continue
        key = (row["grid"], row["scenario"])
        facts = {k: v for k, v in row.items() if k not in ignore}
        other = keyed.get(key)
        if other and {k: v for k, v in other.items() if k in facts} == facts:
            sw, no_sw = (row, other) if row["switches"] else (other, row)
            other["bus_text"] = (
                str(sw["buses"])
                if sw["buses"] == no_sw["buses"]
                else f"{sw['buses']} / {no_sw['buses']}"
            )
            other["buses"] = max(sw["buses"], no_sw["buses"])
        elif other:  # differs beyond the switches: keep both
            keyed[key + (row["code"],)] = {**row, "bus_text": str(row["buses"])}
        else:
            keyed[key] = {**row, "bus_text": str(row["buses"])}
    return list(keyed.values())


def _name(row: dict) -> str:
    return f"`{re.sub(r'-(no_)?sw$', '', row['code'])}`"


def _table(rows: list[dict], columns: list[tuple[str, Any]]) -> str:
    head = "| " + " | ".join(c for c, _ in columns) + " |"
    rule = "|" + "|".join("---" for _ in columns) + "|"
    body = ["| " + " | ".join(str(f(r)) for _, f in columns) + " |" for r in rows]
    return "\n".join([head, rule, *body])


FACTS = [
    ("Network", _name),
    ("Buses", lambda r: r["bus_text"]),
    ("Lines / trafos", lambda r: f"{r['lines']} / {r['trafos']}"),
    (
        "Loads / sgens / storage",
        lambda r: f"{r['loads']} / {r['sgens']} / {r['storage']}",
    ),
    ("Load", lambda r: _kw(r["load_kw"])),
    ("Generation", lambda r: _kw(_gen(r))),
    ("Gen / load", lambda r: _pct(_gen(r), r["load_kw"])),
    (
        "PV / load",
        lambda r: _pct(r["generation_kw_by_class"].get("pv", 0), r["load_kw"]),
    ),
    ("Load buses", lambda r: r["load_buses"]),
    ("Prosumer buses", lambda r: r["prosumer_buses"]),
    ("Ratings", lambda r: _yes(r["line_ratings"])),
    ("Geodata", lambda r: _yes(r["geodata"])),
]


def _mix(row: dict) -> str:
    """Load counts by class, largest first, e.g. ``Households 32 · Commercial 9``."""
    counts = sorted(row["loads_by_class"].items(), key=lambda kv: -kv[1])
    return " · ".join(f"{LOAD_CLASSES.get(k, k)} {n}" for k, n in counts) or "—"


def _generation_mix(row: dict) -> str:
    kw = sorted(row["generation_kw_by_class"].items(), key=lambda kv: -kv[1])
    return " · ".join(f"{GENERATION.get(k, k)} {_kw(v)}" for k, v in kw if v) or "—"


def render_blocks(rows: list[dict]) -> dict[str, str]:
    """Markdown for every generated block of the page, by key."""
    merged = _merge_switch_variants(rows)
    simbench = [r for r in merged if r["type"] == "simbench"]
    builtin = [r for r in merged if r["type"] != "simbench"]
    blocks: dict[str, str] = {}

    levels = [lvl for lvl in LEVELS if any(r["level"] == lvl for r in simbench)]
    levels += sorted({r["level"] for r in simbench} - set(levels))
    overview = []
    for lvl in levels:
        group = [r for r in simbench if r["level"] == lvl]
        overview.append(
            {
                "level": lvl,
                "grids": len({r["grid"] for r in group}),
                "rows": len(group),
                "buses": f"{min(r['buses'] for r in group)}–{max(r['buses'] for r in group)}",
                "loads": f"{min(r['loads'] for r in group)}–{max(r['loads'] for r in group)}",
                "load": f"{_kw(min(r['load_kw'] for r in group))} – {_kw(max(r['load_kw'] for r in group))}",
                "pv": f"{mean(100 * r['generation_kw_by_class'].get('pv', 0) / r['load_kw'] for r in group if r['load_kw']):.0f} %",
            }
        )
    blocks["overview"] = _table(
        overview,
        [
            ("Level", lambda r: r["level"]),
            ("Grids", lambda r: r["grids"]),
            ("Grid × scenario", lambda r: r["rows"]),
            ("Buses", lambda r: r["buses"]),
            ("Loads", lambda r: r["loads"]),
            ("Rated load", lambda r: r["load"]),
            ("Mean PV / load", lambda r: r["pv"]),
        ],
    )

    blocks["levels"] = "\n\n".join(
        f"### {lvl}\n\n"
        + _table(
            sorted(
                (r for r in simbench if r["level"] == lvl),
                key=lambda r: (r["grid"], r["scenario"]),
            ),
            FACTS,
        )
        for lvl in levels
    )
    blocks["mix"] = _table(
        sorted(
            simbench,
            key=lambda r: (
                LEVELS.index(r["level"]) if r["level"] in LEVELS else 99,
                r["grid"],
                r["scenario"],
            ),
        ),
        [
            ("Network", _name),
            ("Loads by type", _mix),
            ("Generation by type", _generation_mix),
            (
                "Storage",
                lambda r: (
                    f"{r['storage']} ({_kw(r['storage_kw'])})" if r["storage"] else "—"
                ),
            ),
        ],
    )
    blocks["builtin"] = _table(
        builtin,
        [
            ("Network", _name),
            ("Label", lambda r: r["label"]),
            ("Level", lambda r: r["level"]),
        ]
        + FACTS[1:],
    )

    # rankings
    def top(key, n=10, rows_=simbench, reverse=True):
        return sorted(rows_, key=key, reverse=reverse)[:n]

    pv = lambda r: (
        r["generation_kw_by_class"].get("pv", 0) / r["load_kw"] if r["load_kw"] else 0
    )  # noqa: E731
    ranking_cols = [
        ("Network", _name),
        ("Level", lambda r: r["level"]),
        (
            "PV / load",
            lambda r: _pct(r["generation_kw_by_class"].get("pv", 0), r["load_kw"]),
        ),
        ("Gen / load", lambda r: _pct(_gen(r), r["load_kw"])),
        ("Prosumer buses", lambda r: f"{r['prosumer_buses']} of {r['load_buses']}"),
        ("Load", lambda r: _kw(r["load_kw"])),
        ("Buses", lambda r: r["bus_text"]),
        (
            "EV / HP loads",
            lambda r: r["loads_by_class"].get("ev", 0)
            + r["loads_by_class"].get("heat_pump", 0),
        ),
        ("Storage", lambda r: r["storage"]),
    ]
    lv = [r for r in simbench if r["level"] == "LV"]
    sections = [
        (
            "Low-voltage networks (local markets), by PV penetration",
            sorted(lv, key=pv, reverse=True),
        ),
        (
            "Medium-voltage networks, by generation / load",
            sorted(
                (r for r in simbench if r["level"] == "MV"),
                key=lambda r: _gen(r) / r["load_kw"],
                reverse=True,
            ),
        ),
        (
            "All networks: most prosumer buses (candidate agents)",
            top(lambda r: r["prosumer_buses"]),
        ),
        (
            "All networks: most EV charging and heat-pump loads",
            top(
                lambda r: r["loads_by_class"].get("ev", 0)
                + r["loads_by_class"].get("heat_pump", 0)
            ),
        ),
        (
            "All networks: most storage units",
            sorted([r for r in simbench if r["storage"]], key=lambda r: -r["storage"])[
                :10
            ],
        ),
    ]
    blocks["rankings"] = "\n\n".join(
        f"**{title}**\n\n" + _table(rows_, ranking_cols) for title, rows_ in sections
    )

    # scenarios: the same grid in scenario 0, 1, 2
    grids = sorted(
        {r["grid"] for r in simbench},
        key=lambda g: (
            LEVELS.index(g.split("-")[1]) if g.split("-")[1] in LEVELS else 99,
            g,
        ),
    )
    scen_rows = []
    for g in grids:
        by = {r["scenario"]: r for r in simbench if r["grid"] == g}
        scen_rows.append({"grid": g, **{s: by.get(s) for s in (0, 1, 2)}})

    def cell(r):
        if r is None:
            return "—"
        return (
            f"{_pct(r['generation_kw_by_class'].get('pv', 0), r['load_kw'])} PV · "
            f"{r['loads_by_class'].get('ev', 0) + r['loads_by_class'].get('heat_pump', 0)} EV/HP · "
            f"{r['storage']} storage"
        )

    blocks["scenarios"] = _table(
        scen_rows,
        [("Grid", lambda r: f"`{r['grid']}`")]
        + [(f"Scenario {s}", lambda r, s=s: cell(r[s])) for s in (0, 1, 2)],
    )
    blocks["generated"] = (
        f"{len(rows)} networks ({len(simbench)} SimBench grid × scenario rows after "
        f"merging the switch variants, {len(builtin)} pandapower built-ins), "
        f"from `docs_thesis/guide/networks.json`."
    )
    return blocks


def write(check: bool = False) -> int:
    """Fill the page's blocks from networks.json; with ``check``, only compare."""
    rows = json.loads(DATA.read_text(encoding="utf-8"))
    blocks = render_blocks(rows)
    text = PAGE.read_text(encoding="utf-8")
    new = BLOCK.sub(lambda m: m.group(1) + blocks[m.group(2)] + "\n" + m.group(3), text)
    if check:
        if new != text:
            print(
                "guide/networks.md is out of date; run python docs_thesis/networks.py"
            )
            return 1
        return 0
    if new != text:
        PAGE.write_text(new, encoding="utf-8", newline="\n")
        print("updated: guide/networks.md")
    return 0


def main(argv: list[str]) -> int:
    if "--collect" in argv:
        rows = collect()
        DATA.write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {DATA} ({len(rows)} networks)")
    return write(check="--check" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
