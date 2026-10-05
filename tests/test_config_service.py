"""The real ConfigService: presets, the workspace library, diff and bundles."""

import json
import zipfile
from pathlib import Path

import pytest

from src_thesis.platform.services.container import build_services
from src_thesis.platform.services.config_service import ConfigService
from src_thesis.platform.services.workspace import PRESETS_DIR, Workspace, default_home
from src_thesis.platform.experiments.models import expand, files

PRESET = "case6-3x3"


@pytest.fixture()
def config(tmp_path: Path) -> ConfigService:
    return ConfigService(Workspace(tmp_path / "home"))


def test_presets_are_listed_and_valid(config: ConfigService) -> None:
    presets = config.list(kind="preset")
    assert {p.id for p in presets} == {
        "case1-mechanisms",
        "case2-heterogeneity",
        "case3-dso-strategies",
        "case4-grid-constraints",
        "case5-battery",
        "case6-3x3",
        "case7-scalability",
    }
    for summary in presets:
        file = config.load(summary.id)
        assert file.meta.id == summary.id
        resolved = config.resolve(file)
        assert config.expand(resolved)
        for p in file.participants:  # owned loads sit on the agent's bus
            assert p.bus and p.owns.loads


def test_new_from_preset_writes_a_library_file(config: ConfigService) -> None:
    first = config.new_from_preset(PRESET)
    second = config.new_from_preset(PRESET)
    assert (first.meta.id, second.meta.id) == (f"{PRESET}-draft", f"{PRESET}-draft-2")
    assert first.meta.derived_from == f"preset:{PRESET}"
    assert "preset" not in first.meta.tags
    assert (config.library_dir / f"{first.meta.id}.marlem.json").exists()
    assert {d.id for d in config.list(kind="draft")} == {first.meta.id, second.meta.id}


def test_save_and_load_round_trip(config: ConfigService) -> None:
    file = config.new_from_preset(PRESET)
    file.market.mechanism = "buyer"
    path = config.save(file)
    loaded = config.load(file.meta.id)
    assert loaded == file
    assert config.hash(loaded) == files.canonical_hash(file)
    assert json.loads(Path(path).read_text(encoding="utf-8"))["meta"]["id"] == (
        file.meta.id
    )


def test_presets_cannot_be_overwritten(config: ConfigService) -> None:
    preset = config.load(PRESET)
    with pytest.raises(ValueError, match="preset ID"):
        config.save(preset)


@pytest.mark.parametrize("bad", ["../escape", "a b", "a__b", "", "-x"])
def test_ids_must_be_path_safe(config: ConfigService, bad: str) -> None:
    file = config.new_from_preset(PRESET)
    file.meta.id = bad
    with pytest.raises(ValueError, match="Invalid experiment ID"):
        config.save(file)


def test_clone(config: ConfigService) -> None:
    clone = config.clone(PRESET, "my-study")
    assert clone.meta.derived_from == PRESET
    assert config.load("my-study").meta.id == "my-study"
    with pytest.raises(FileExistsError):
        config.clone(PRESET, "my-study")
    with pytest.raises(FileNotFoundError):
        config.load("missing")


def test_diff_reports_dotted_paths(config: ConfigService) -> None:
    a = config.load(PRESET)
    b = a.model_copy(deep=True)
    b.market.mechanism = "seller"
    b.participants[2].bus = "LV4.101 Bus 1"
    changes = {c.path: (c.before, c.after) for c in config.diff(a, b)}
    assert changes == {
        "market.mechanism": ("average", "seller"),
        "participants[2].bus": (a.participants[2].bus, "LV4.101 Bus 1"),
    }
    assert config.diff(a, a) == []


def test_expand_matches_the_experiment_layer(config: ConfigService) -> None:
    file = config.load("case1-mechanisms")
    assert config.expand(file) == expand.expand(file)


def test_export_bundle_contains_the_file_and_its_data(
    config: ConfigService, tmp_path: Path
) -> None:
    csv = tmp_path / "tariff.csv"
    csv.write_text("hour,price\n0,0.2\n", encoding="utf-8")
    file = config.new_from_preset(PRESET)
    file = config.update(
        file,
        {
            "dso.tariffs.feed_in": {"path": str(csv), "column": "price"},
            "dso.tariffs.utility": {"path": str(tmp_path / "missing.csv")},
        },
    )
    with zipfile.ZipFile(config.export_bundle(file)) as bundle:
        names = bundle.namelist()
    assert f"{file.meta.id}.marlem.json" in names
    assert sum(n.endswith("tariff.csv") for n in names) == 1
    assert not any(n.endswith("missing.csv") for n in names)


def test_import_file_and_bundle_round_trip(
    config: ConfigService, tmp_path: Path
) -> None:
    csv = tmp_path / "tariff.csv"
    csv.write_text("hour,price\n0,0.2\n", encoding="utf-8")
    file = config.new_from_preset(PRESET)
    file = config.update(
        file, {"dso.tariffs.feed_in": {"path": str(csv), "column": "price"}}
    )
    bundle = Path(config.export_bundle(file)).read_bytes()
    imported = config.import_bundle(bundle)
    assert imported.meta.id == f"{file.meta.id}-2"  # the original ID is taken
    path = Path(imported.dso.tariffs.feed_in.path)
    assert path.read_text(encoding="utf-8").startswith("hour,price")
    assert "imports" in path.parts
    again = config.import_file(files.dumps(file).encode())
    assert again.meta.id == f"{file.meta.id}-3"
    assert config.load(again.meta.id).market == file.market
    with pytest.raises(ValueError):
        config.import_file(b'{"kind": "something-else"}')


def test_container_and_default_home(tmp_path: Path, monkeypatch) -> None:
    services = build_services(home=tmp_path)
    assert isinstance(services.config, ConfigService)
    assert services.config.workspace.library == tmp_path / "library"
    assert services.sample_data() == [
        "validation",
        "experiments",
        "results",
    ]
    monkeypatch.setenv("MARLEM_HOME", str(tmp_path / "elsewhere"))
    assert default_home() == tmp_path / "elsewhere"
    monkeypatch.delenv("MARLEM_HOME")
    assert "onedrive" not in str(default_home()).lower()
    assert PRESETS_DIR.is_dir()


def test_update_sets_dotted_paths_and_validates(config: ConfigService) -> None:
    file = config.new_from_preset(PRESET)
    updated = config.update(
        file, {"market.mechanism": "seller", "dso.fees.zone_factor": 1.0}
    )
    assert updated.market.mechanism == "seller"
    assert updated.dso.fees.zone_factor == 1.0
    assert file.market.mechanism == "average"  # the input is not changed
    with pytest.raises(ValueError):
        config.update(file, {"meta.data_status": "made-up"})


def test_unknown_or_mistyped_fields_are_rejected(config: ConfigService) -> None:
    file = config.new_from_preset(PRESET)
    for change in (
        {"dso.fees.zone_factr": 1.0},  # misspelt
        {"market.mechanism": "cheapest"},  # not a mechanism
        {"learning.seeds": ["one"]},  # not integers
        {"participants": [{"id": "a", "bsu": "x"}]},  # misspelt participant field
    ):
        with pytest.raises(ValueError):
            config.update(file, change)


def test_files_round_trip_unchanged(config: ConfigService) -> None:
    for preset in config.list(kind="preset"):
        text = config.presets_dir.joinpath(Path(preset.path).name).read_text("utf-8")
        assert files.dumps(files.parse(text)) == json.dumps(
            json.loads(text), indent=2, ensure_ascii=False
        )


def test_origin_and_delete(config: ConfigService) -> None:
    draft = config.new_from_preset(PRESET)
    assert config.origin(draft).meta.id == PRESET
    clone = config.clone(draft.meta.id, "my-copy")
    assert config.origin(clone).meta.id == draft.meta.id
    config.delete("my-copy")
    with pytest.raises(FileNotFoundError):
        config.load("my-copy")
    with pytest.raises(FileNotFoundError):
        config.delete(PRESET)  # presets are not in the library
    clone.meta.derived_from = "preset:gone"
    assert config.origin(clone) is None


def test_workspace_folder_choice(tmp_path: Path, monkeypatch) -> None:
    from src_thesis.platform.services import workspace

    monkeypatch.setattr(workspace, "settings_path", lambda: tmp_path / "s.json")
    monkeypatch.delenv("MARLEM_HOME", raising=False)
    assert workspace.home_source() == "default"
    assert workspace.default_home() == workspace.built_in_home()

    chosen = workspace.set_home(tmp_path / "my-runs")
    assert chosen.is_dir() and workspace.default_home() == chosen
    assert workspace.home_source() == "settings"

    monkeypatch.setenv("MARLEM_HOME", str(tmp_path / "env"))
    assert workspace.default_home() == tmp_path / "env"  # the variable wins
    assert workspace.home_source() == "environment"
    monkeypatch.delenv("MARLEM_HOME")

    assert workspace.set_home(None) == workspace.built_in_home()
    assert workspace.home_source() == "default"
    assert workspace.is_synced_folder(Path("C:/Users/x/OneDrive/Desktop"))


def test_synced_folder_detection() -> None:
    from src_thesis.platform.services.workspace import is_synced_folder

    assert is_synced_folder(Path("C:/Users/x/OneDrive/Desktop/runs"))
    assert is_synced_folder(Path("C:/Users/x/OneDrive - TalTech/runs"))
    assert not is_synced_folder(Path("C:/temp/c--Users-x-OneDrive-Desktop/runs"))
