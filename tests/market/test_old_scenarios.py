"""Scenario files saved while the graph model existed (``grid.method``,
``graph_capacity``, ``graph_total_kw``) still load: the keys are dropped."""

from __future__ import annotations

from dataclasses import fields

from core.config import store
from core.config.scenario import GridSetup


def test_a_scenario_with_the_removed_graph_settings_loads():
    old = {
        "name": "old",
        "grid": {
            "code": "1-LV-rural1--0-sw",
            "day": "2016-06-15",
            "method": "graph",
            "graph_capacity": "ratings",
            "graph_total_kw": 1800.0,
            "load_scale": 2.0,
        },
        "participants": [],
    }
    scenario = store.from_dict(old)
    assert scenario.grid.code == "1-LV-rural1--0-sw" and scenario.grid.load_scale == 2.0
    names = {f.name for f in fields(GridSetup)}
    assert not names & {"method", "graph_capacity", "graph_total_kw"}
