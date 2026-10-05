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

from src_thesis.marlem.grid import placement as mapping  # noqa: E402
from src_thesis.platform.services.config_service import ConfigService  # noqa: E402
from src_thesis.platform.services.models import NetworkSource  # noqa: E402
from src_thesis.platform.services.participant_service import (  # noqa: E402
    ParticipantService,
)
from src_thesis.platform.services.profile_service import ProfileService  # noqa: E402
from src_thesis.platform.services.tariff_service import TariffService  # noqa: E402
from src_thesis.platform.services.workspace import Workspace  # noqa: E402

LV = NetworkSource(type="simbench", code="1-LV-semiurb4--0-sw")


@pytest.fixture(scope="module")
def participants() -> ParticipantService:
    return ParticipantService()


@pytest.fixture()
def tariffs() -> TariffService:
    return TariffService()


@pytest.fixture()
def draft(tmp_path: Path):
    return ConfigService(Workspace(tmp_path / "home")).new_from_preset("case6-3x3")


RURAL = NetworkSource(type="simbench", code="1-LV-rural1--2-no_sw")


@pytest.mark.parametrize("position", ["anywhere", "spread"])
def test_placement_is_reproducible_and_consistent(participants, position) -> None:
    rule = {"position": position, "n": 6, "seed": 3}
    placed = participants.suggest_mapping(LV, rule)
    assert placed == participants.suggest_mapping(LV, rule) and len(placed) == 6
    elements = {e.id: e for e in profiles_elements(LV)}
    owned = [e for p in placed for side in p["owns"].values() for e in side]
    assert len(owned) == len(set(owned))  # nothing owned twice
    assert len({p["bus"] for p in placed}) == 6  # one agent per bus
    for p in placed:
        assert p["profile"] == {"source": "native"}
        assert all(elements[e].bus == p["bus"] for e in owned if e in p_owned(p))


def p_owned(p: dict) -> list[str]:
    return [e for side in p["owns"].values() for e in side]


def profiles_elements(source):
    from src_thesis.platform.services.container import build_services

    return build_services().grid.elements(source)


def test_filters_combine_any_load_type(participants) -> None:
    # 1-LV-rural1--2-no_sw: 8 buses with PV, only 3 of them with a household load.
    households = {"loads": ["household"], "generation": "pv"}
    assert len(participants.placement_candidates(RURAL, households)) == 3
    prosumers = participants.placement_candidates(RURAL, {"generation": "pv"})
    assert len(prosumers) == 8
    farms = participants.placement_candidates(
        RURAL, {"loads": ["agricultural"], "generation": "pv"}
    )
    assert len(farms) == 5
    options = participants.placement_options(RURAL)
    assert {"household", "agricultural", "ev", "heat_pump"} <= set(options["loads"])


def test_agents_own_their_whole_bus_or_only_matching_loads(participants) -> None:
    rule = {"loads": ["household"], "generation": "pv", "n": 3, "seed": 1}
    whole = participants.suggest_mapping(RURAL, rule)
    matching = participants.suggest_mapping(RURAL, {**rule, "owns": "matching"})
    elements = {e.id: e for e in profiles_elements(RURAL)}
    for p in whole:  # every element at the bus, EV chargers and heat pumps too
        at_bus = {e.id for e in elements.values() if e.bus == p["bus"]}
        assert set(p_owned(p)) == at_bus
    for p in matching:
        assert all(
            elements[e].profile_type.startswith("H0-") for e in p["owns"]["loads"]
        )
        assert p["owns"]["sgens"]


def test_placement_rejects_too_many_agents(participants) -> None:
    with pytest.raises(ValueError, match="fewer than"):
        participants.suggest_mapping(LV, {"position": "feeder_ends", "n": 500})
    with pytest.raises(ValueError, match="Unknown generation"):
        participants.suggest_mapping(LV, {"generation": "nope"})


def test_scaling_to_peak_and_energy() -> None:
    year = [0.0, 1.0, 2.0, 1.0]
    assert mapping.scale([2.0], year, "peak_kw", 10, 1.0) == [10.0]
    assert mapping.scale([1.0], year, "energy_kwh", 8, 1.0) == [2.0]
    assert mapping.scale([3.0], year, "none", None, 1.0) == [3.0]
    with pytest.raises(ValueError):
        mapping.scale([1.0], year, "peak_kw", None, 1.0)


def test_preview_scales_catalogue_profiles(participants, draft) -> None:
    p = draft.participants[0]  # catalog G1-A / PV3, peak 180 kW
    series = participants.preview(draft, p.id, days=2)
    assert len(series.x) == 48 and series.y_label == "kW"
    assert 0 < max(series.y["demand"]) <= 180.01
    assert 0 < max(series.y["generation"]) <= 180.01
    net = series.y["net (generation − demand)"]
    assert net[12] == pytest.approx(
        series.y["generation"][12] - series.y["demand"][12], abs=0.02
    )


def test_preview_of_native_participants(participants, draft, tmp_path) -> None:
    placed = participants.suggest_mapping(LV, {"n": 2, "seed": 1})
    file = ConfigService(Workspace(tmp_path / "x")).update(
        draft, {"participants": placed}
    )
    series = participants.preview(file, placed[0]["id"], days=1)
    assert len(series.y["demand"]) == 24 and max(series.y["demand"]) > 0


def test_days_follow_the_time_section(draft, tmp_path) -> None:
    split = ConfigService(Workspace(tmp_path / "c")).days(draft)
    assert split["train"] and split["eval"]
    assert not set(split["train"]) & set(split["eval"])


def test_import_mapping_from_csv_and_json(participants) -> None:
    text = (
        "id,role,bus,loads,sgens,profile_source,demand,generation,scaling_mode,"
        "demand_target,generation_target,battery_kwh\n"
        "a1,home,LV4.101 Bus 18,LV4.101 Load 1,,catalog,H0-A,PV3,peak_kw,5,4,10\n"
    )
    rows = participants.import_mapping(text.encode(), "map.csv")
    assert rows[0]["owns"]["loads"] == ["LV4.101 Load 1"]
    assert rows[0]["profile"]["demand"] == {"type": "H0-A"}
    assert rows[0]["scaling"] == {"mode": "peak_kw", "demand": 5.0, "generation": 4.0}
    assert rows[0]["battery"] == {"nominal_capacity_kwh": 10.0}
    back = participants.import_mapping(
        json.dumps({"participants": rows}).encode(), "m.json"
    )
    assert back == rows
    with pytest.raises(ValueError):
        participants.import_mapping(b'[{"id": "x"}]', "m.json")


def test_paper_roles_keep_placement(participants, draft) -> None:
    roles = participants.paper_roles(draft.participants)
    assert [p["id"] for p in roles][:2] == ["small_industry", "community_hospital"]
    assert roles[1]["battery"]["nominal_capacity_kwh"] == 85.0  # [P2] Table 6
    assert roles[1]["bus"] == draft.participants[1].bus


def test_tariffs_read_the_csvs(tariffs, draft, tmp_path) -> None:
    series = tariffs.tariffs(draft)  # csv without files: the original defaults
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
    assert "utility · profile_2" in tariffs.tariffs(file).y
    synthetic = ConfigService(Workspace(tmp_path / "z")).update(
        draft, {"dso.tariffs.source": "synthetic"}
    )
    assert tariffs.tariffs(synthetic).y == {}
    assert "data/prices/fit_60min.csv" in tariffs.tariff_files()
    with pytest.raises(ValueError):
        ProfileService().data_files("../src_thesis")
