"""Participant mapping and the ProfileService methods behind the Build pages.

Placement rules and scaling (01 §3), profile previews, the day split, mapping
imports, the [P2] Table 6 roles and the DSO tariff CSVs. Loads a real SimBench
network, so it needs `simbench` and `pandapower` (conda env `marlem`).
"""

import json
from pathlib import Path

import pytest

pytest.importorskip("pandapower")
pytest.importorskip("simbench")

from src_thesis.adapters.grid import participants as mapping  # noqa: E402
from src_thesis.application.config_service import ConfigService  # noqa: E402
from src_thesis.application.models import NetworkSource  # noqa: E402
from src_thesis.application.profile_service import ProfileService  # noqa: E402
from src_thesis.application.workspace import Workspace  # noqa: E402

LV = NetworkSource(type="simbench", code="1-LV-semiurb4--0-sw")


@pytest.fixture(scope="module")
def profiles() -> ProfileService:
    return ProfileService()


@pytest.fixture()
def draft(tmp_path: Path):
    return ConfigService(Workspace(tmp_path / "home")).new_from_preset("case6-3x3")


@pytest.mark.parametrize("rule", ["by_elements", "spread"])
def test_placement_is_reproducible_and_consistent(profiles, rule) -> None:
    placed = profiles.suggest_mapping(LV, {"type": rule, "n": 6, "seed": 3})
    again = profiles.suggest_mapping(LV, {"type": rule, "n": 6, "seed": 3})
    assert placed == again and len(placed) == 6
    elements = {e.id: e for e in profiles_elements()}
    owned = [e for p in placed for side in p["owns"].values() for e in side]
    assert len(owned) == len(set(owned))  # nothing owned twice
    for p in placed:
        assert p["profile"] == {"source": "native"}
        assert all(elements[e].bus == p["bus"] for e in p["owns"]["loads"])


def profiles_elements():
    from src_thesis.application.container import build_services

    return build_services().grid.elements(LV)


def test_placement_rejects_too_many_agents(profiles) -> None:
    with pytest.raises(ValueError, match="fewer than"):
        profiles.suggest_mapping(LV, {"type": "feeder_ends", "n": 500})
    with pytest.raises(ValueError, match="Unknown placement rule"):
        profiles.suggest_mapping(LV, {"type": "nope"})


def test_scaling_to_peak_and_energy() -> None:
    year = [0.0, 1.0, 2.0, 1.0]
    assert mapping.scale([2.0], year, "peak_kw", 10, 1.0) == [10.0]
    assert mapping.scale([1.0], year, "energy_kwh", 8, 1.0) == [2.0]
    assert mapping.scale([3.0], year, "none", None, 1.0) == [3.0]
    with pytest.raises(ValueError):
        mapping.scale([1.0], year, "peak_kw", None, 1.0)


def test_preview_scales_catalogue_profiles(profiles, draft) -> None:
    p = draft.participants[0]  # catalog G1-A / PV3, peak 180 kW
    series = profiles.preview(draft, p["id"], days=2)
    assert len(series.x) == 48 and series.y_label == "kW"
    assert 0 < max(series.y["demand"]) <= 180.01
    assert 0 < max(series.y["generation"]) <= 180.01
    net = series.y["net (generation − demand)"]
    assert net[12] == pytest.approx(
        series.y["generation"][12] - series.y["demand"][12], abs=0.02
    )


def test_preview_of_native_participants(profiles, draft, tmp_path) -> None:
    placed = profiles.suggest_mapping(LV, {"type": "by_elements", "n": 2, "seed": 1})
    file = ConfigService(Workspace(tmp_path / "x")).update(
        draft, {"participants": placed}
    )
    series = profiles.preview(file, placed[0]["id"], days=1)
    assert len(series.y["demand"]) == 24 and max(series.y["demand"]) > 0


def test_days_follow_the_time_section(profiles, draft) -> None:
    split = profiles.days(draft)
    assert split["train"] and split["eval"]
    assert not set(split["train"]) & set(split["eval"])


def test_import_mapping_from_csv_and_json(profiles) -> None:
    text = (
        "id,role,bus,loads,sgens,profile_source,demand,generation,scaling_mode,"
        "demand_target,generation_target,battery_kwh\n"
        "a1,home,LV4.101 Bus 18,LV4.101 Load 1,,catalog,H0-A,PV3,peak_kw,5,4,10\n"
    )
    rows = profiles.import_mapping(text.encode(), "map.csv")
    assert rows[0]["owns"]["loads"] == ["LV4.101 Load 1"]
    assert rows[0]["profile"]["demand"] == {"type": "H0-A"}
    assert rows[0]["scaling"] == {"mode": "peak_kw", "demand": 5.0, "generation": 4.0}
    assert rows[0]["battery"] == {"nominal_capacity_kwh": 10.0}
    back = profiles.import_mapping(
        json.dumps({"participants": rows}).encode(), "m.json"
    )
    assert back == rows
    with pytest.raises(ValueError):
        profiles.import_mapping(b'[{"id": "x"}]', "m.json")


def test_paper_roles_keep_placement(profiles, draft) -> None:
    roles = profiles.paper_roles(draft.participants)
    assert [p["id"] for p in roles][:2] == ["small_industry", "community_hospital"]
    assert roles[1]["battery"]["nominal_capacity_kwh"] == 85.0  # [P2] Table 6
    assert roles[1]["bus"] == draft.participants[1]["bus"]


def test_tariffs_read_the_csvs(profiles, draft, tmp_path) -> None:
    series = profiles.tariffs(draft)  # csv without files: the original defaults
    assert len(series.x) == 24 and series.x[0] == "00:00"
    assert any(k.startswith("feed-in") for k in series.y)
    file = ConfigService(Workspace(tmp_path / "y")).update(
        draft,
        {
            "dso.tariffs.utility": {
                "path": "data/prices/utility_15min.csv",
                "column": "profile_2",
            }
        },
    )
    assert "utility · profile_2" in profiles.tariffs(file).y
    synthetic = ConfigService(Workspace(tmp_path / "z")).update(
        draft, {"dso.tariffs.source": "synthetic"}
    )
    assert profiles.tariffs(synthetic).y == {}
    assert "data/prices/fit_60min.csv" in profiles.tariff_files()
    with pytest.raises(ValueError):
        profiles.data_files("../src_thesis")
