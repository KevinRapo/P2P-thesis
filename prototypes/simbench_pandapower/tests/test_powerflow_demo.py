from powerflow_demo import run_demo


def test_simbench_feeder_solves_for_all_three_prototype_scenarios() -> None:
    results = run_demo()

    assert [result.scenario for result in results] == [
        "base",
        "double_selected_load",
        "add_pv_at_selected_bus",
    ]
    assert all(result.converged for result in results)
    assert all(0.5 < result.min_voltage_pu < 1.5 for result in results)
    assert all(result.max_line_loading_percent >= 0 for result in results)
    assert results[1].selected_load_kw == results[0].selected_load_kw * 2
    assert results[2].added_pv_kw == 5.0
