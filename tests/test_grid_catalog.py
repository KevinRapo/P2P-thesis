"""The real grid catalog: SimBench and pandapower built-in networks (01 §1–§2).

Loads real networks, so it needs `simbench` and `pandapower` (conda env `marlem`).
"""

import pytest

pytest.importorskip("pandapower")
pytest.importorskip("simbench")

from src_thesis.application.container import build_services  # noqa: E402
from src_thesis.application.models import NetworkSource  # noqa: E402

LV = NetworkSource(type="simbench", code="1-LV-semiurb4--0-sw")
CASE33 = NetworkSource(type="pandapower_builtin", code="case33bw")


@pytest.fixture(scope="module")
def grid():
    return build_services().grid


def test_catalog_lists_simbench_by_level(grid) -> None:
    lv = grid.list_networks("simbench", level="LV")
    assert lv and all(n.voltage_level == "LV" for n in lv)
    assert LV.code in {n.source.code for n in lv}
    assert not any("complete_data" in n.source.code for n in grid.list_networks())


def test_summary_counts_the_loaded_network(grid) -> None:
    s = grid.summary(LV)
    assert (s.info.buses, s.info.loads, s.info.sgens) == (44, 41, 1)
    assert s.info.has_profiles and s.info.has_line_ratings and s.info.has_geodata
    assert s.profile_year == 2016


def test_topology_is_consistent(grid) -> None:
    t = grid.topology(LV)
    ids = {b["id"] for b in t.buses}
    assert len(ids) == len(t.buses) == 44
    assert all(br["from"] in ids and br["to"] in ids for br in t.lines)
    assert t.external_grid_bus in ids
    assert sum(br["kind"] == "trafo" for br in t.lines) == 1


def test_elements_filter_by_bus(grid) -> None:
    every = grid.elements(LV)
    assert len(every) == 42
    bus = every[0].bus
    assert {e.bus for e in grid.elements(LV, bus)} == {bus}


def test_preview_uses_the_simbench_profiles(grid) -> None:
    noon = grid.preview_powerflow(LV, "2016-06-15", 12)
    night = grid.preview_powerflow(LV, "2016-06-15", 3)
    assert noon.converged and night.converged
    assert len(noon.bus_voltage_pu) == 44
    assert noon.external_grid_kw != night.external_grid_kw
    with pytest.raises(ValueError):
        grid.preview_powerflow(LV, "2017-01-01", 12)


def test_builtin_network_without_profiles_or_ratings(grid) -> None:
    s = grid.summary(CASE33)
    assert not s.info.has_profiles and not s.info.has_line_ratings
    p = grid.preview_powerflow(CASE33, "2016-06-15", 12)
    assert p.converged and p.max_line_loading_percent is None
    assert any("static" in n for n in p.notes)


def test_external_grid_is_drawn_at_its_transformer(grid) -> None:
    """The upstream bus keeps its SimBench position far away; it is drawn next to
    the transformer's other side instead."""
    topo = grid.topology(NetworkSource(type="simbench", code="1-LV-semiurb4--1-sw"))
    pos = {b["id"]: (b["x"], b["y"]) for b in topo.buses}
    trafo = next(br for br in topo.lines if br["kind"] == "trafo")
    ext = topo.external_grid_bus
    other = trafo["to"] if trafo["from"] == ext else trafo["from"]
    ys = [y for _, y in pos.values()]
    span = max(ys) - min(ys)
    assert abs(pos[ext][0] - pos[other][0]) < 1e-9
    assert 0 < pos[ext][1] - pos[other][1] <= 0.05 * span


def test_simbench_profiles_can_be_inspected() -> None:
    profiles = build_services().profiles
    types = profiles.profile_types(LV)
    codes = {t.code for t in types}
    assert {"H0-A", "PV5"} <= codes
    h0a = next(t for t in types if t.code == "H0-A")
    assert h0a.category == "household" and h0a.quantities == ["p", "q"]
    assert h0a.elements > 0 and 0 < h0a.mean < h0a.peak <= 1.0
    day = profiles.profile_series(LV, ["H0-A", "PV5"], "2016-06-15", 1, "15min")
    assert len(day.x) == 96 and day.x[0] == "2016-06-15 00:00"
    assert max(day.y["PV5"]) > 0 and day.y["PV5"][0] == 0  # sun at noon, not at night
    year = profiles.profile_series(LV, ["H0-A"], "2016-01-01", 366, "daily")
    assert len(year.x) == 366
    assert profiles.profile_series(LV, ["PV5"], "2016-06-15", 1, "hourly", "q").y == {}
    assert profiles.profile_types(CASE33) == []


def test_complete_simbench_profile_catalogue() -> None:
    profiles = build_services().profiles
    types = {t.code: t for t in profiles.catalogue_types()}
    assert len(types) > 400  # far more than any single network uses
    assert types["H0-A"].category == "household"
    assert types["WP4"].category == "wind"
    assert types["Hydro1"].category == "hydro"
    assert types["Air_Parallel_1"].category == "heat_pump"
    assert types["HLS_A_11.0"].category == "ev"
    assert types["HS0"].category == "hv_grid"
    assert types["lv_rural1"].category == "grid"
    assert types["imp0"].category == "exchange"
    pp = [t for t in types.values() if t.code.startswith("pp_")]
    assert pp and all(t.category == "power_plant" for t in pp)
    # Every profile falls into one of SimBench's classes.
    keys = {c.key for c in profiles.profile_classes()}
    assert {t.category for t in types.values()} <= keys
    assert all(t.elements == 0 for t in types.values())
    day = profiles.catalogue_series(["H0-A", "WP4"], "2016-06-15", 1, "hourly")
    assert len(day.x) == 24 and set(day.y) == {"H0-A", "WP4"}
    # A network's profile is the catalogue profile of the same name.
    own = profiles.profile_series(LV, ["H0-A"], "2016-06-15", 1, "hourly")
    assert own.y["H0-A"] == day.y["H0-A"]


def test_profiles_scaled_by_rated_power() -> None:
    profiles = build_services().profiles
    factor = profiles.profile_series(LV, ["H0-A"], "2016-06-15", 1, "hourly")
    summed = profiles.profile_power(LV, ["H0-A"], "2016-06-15", 1, "hourly")
    per_element = profiles.profile_power(
        LV, ["H0-A"], "2016-06-15", 1, "hourly", per_element=True
    )
    h0a = next(t for t in profiles.profile_types(LV) if t.code == "H0-A")
    assert summed.x == factor.x and summed.y_label == "p (kW)"
    assert list(summed.y) == [f"H0-A ({h0a.elements})"]
    assert len(per_element.y) == h0a.elements
    # The sum over the elements equals the per-element series added up.
    total = [sum(v) for v in zip(*per_element.y.values())]
    assert all(
        abs(a - b) < 1e-2 for a, b in zip(summed.y[f"H0-A ({h0a.elements})"], total)
    )
