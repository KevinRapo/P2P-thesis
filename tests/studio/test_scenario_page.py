"""The Scenario page offers every setting of a scenario file."""

from dataclasses import fields
from pathlib import Path

from core.config.scenario import BatterySetup, DsoSetup, GridSetup, MarketSetup

PAGE = Path(__file__).resolve().parents[2] / "studio/pages/scenario.py"


def test_every_scenario_setting_has_a_field_on_the_page():
    source = PAGE.read_text(encoding="utf-8")
    settings = {"prices": ".prices"}

    for setup in (GridSetup, MarketSetup, DsoSetup, BatterySetup):
        for field in fields(setup):
            name = field.name
            if name != "code":  # the network picker
                assert f'"{name}"' in source or settings.get(name, name) in source, name
