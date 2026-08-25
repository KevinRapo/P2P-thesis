import pytest

from studio.domain import GridScenario, IllustrativeGridModel
from studio.service import StudioService


def test_grid_model_changes_results_when_pv_is_added() -> None:
    model = IllustrativeGridModel()
    base = model.run(GridScenario(demand_kw=6, pv_kw=0))
    solar = model.run(GridScenario(demand_kw=6, pv_kw=5))

    assert solar.net_household_kw < base.net_household_kw
    assert solar.max_line_loading_percent < base.max_line_loading_percent
    assert solar.min_voltage_pu > base.min_voltage_pu


def test_battery_discharge_cannot_exceed_demand() -> None:
    with pytest.raises(ValueError, match="cannot exceed"):
        IllustrativeGridModel().run(GridScenario(demand_kw=2, battery_discharge_kw=3))


def test_service_keeps_runs_and_exports_latest_snapshot(tmp_path) -> None:
    service = StudioService()
    snapshot = service.run_grid(GridScenario())
    path = service.save_latest(tmp_path / "latest.json")

    assert service.latest == snapshot
    assert path.exists()
    assert '"run_id": "demo-001"' in path.read_text(encoding="utf-8")
