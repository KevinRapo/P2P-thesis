"""Profile views: units, time windows and catalogue records without loading a grid."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from core.grid import simbench
from core.grid.contract import NetworkRef

REF = NetworkRef("simbench", "fixture")


class Network(SimpleNamespace):
    def __getitem__(self, table):
        return getattr(self, table)


@pytest.fixture
def profiles(monkeypatch):
    factor = np.arange(366 * 96, dtype=float) / 100_000 + 0.1
    network = Network(
        profiles={
            "load": pd.DataFrame(
                {
                    "time": np.arange(len(factor)),
                    "H0_pload": factor,
                    "H0_qload": factor / 2,
                }
            )
        },
        load=pd.DataFrame(
            {
                "name": ["L1", "L2", "static"],
                "profile": ["H0", "H0", None],
                "p_mw": [0.001, 0.002, 0.003],
            },
            index=[0, 2, 7],
        ),
        sgen=pd.DataFrame(),
        storage=pd.DataFrame(),
    )
    absolute = {
        ("load", "p_mw"): pd.DataFrame({0: factor * 0.001, 2: factor * 0.002}),
        ("load", "q_mvar"): pd.DataFrame({0: factor * 0.0005, 2: factor * 0.001}),
    }
    monkeypatch.setattr(simbench, "_load", lambda ref: network)
    monkeypatch.setattr(simbench, "_absolute_profiles", lambda ref: absolute)
    monkeypatch.setattr(simbench, "_catalogue", lambda scenario: network.profiles)

    return network, factor


@pytest.mark.parametrize(
    "resolution,rows", [("15min", 1), ("hourly", 4), ("daily", 96)]
)
@pytest.mark.parametrize("quantity,scale", [("p", 1.0), ("q", 0.5)])
def test_power_views_keep_units_windows_and_sums(
    profiles, resolution, rows, quantity, scale
):
    _, factor = profiles
    expected = factor[96:192].reshape(-1, rows).mean(axis=1) * scale
    x, summed = simbench.profile_power(
        REF, ["H0"], "2016-01-02", 1, resolution, quantity
    )
    _, individual = simbench.profile_power(
        REF, ["H0"], "2016-01-02", 1, resolution, quantity, per_element=True
    )

    assert len(x) == 96 // rows and x[0].startswith("2016-01-02")
    np.testing.assert_allclose(summed["H0 (2)"], np.round(expected * 3, 3), atol=0.001)
    np.testing.assert_allclose(individual["L1 · H0"], np.round(expected, 3), atol=0.001)
    np.testing.assert_allclose(
        individual["L2 · H0"], np.round(expected * 2, 3), atol=0.001
    )


def test_element_views_clip_at_year_end_and_keep_static_power(profiles):
    _, factor = profiles
    x, power = simbench.element_power(REF, ["L1", "static"], "2016-12-31", 2)

    assert len(x) == 24 and x[-1] == "2016-12-31 23:00"
    assert set(power) == {"L1", "static"}
    np.testing.assert_allclose(
        power["L1"], np.round(factor[-96:].reshape(-1, 4).mean(axis=1), 3), atol=0.001
    )
    assert power["static"] == [3.0] * 24


def test_network_and_catalogue_share_profile_descriptions(profiles):
    _, factor = profiles
    network = simbench.profile_catalog(REF)[0]
    catalogue = simbench.catalogue_profiles()[0]

    assert network.elements == 2 and catalogue.elements == 0
    assert network.name == catalogue.name == "H0"
    assert network.quantities == catalogue.quantities == ("p", "q")
    assert network.mean == catalogue.mean == round(float(factor.mean()), 4)
    assert network.peak == catalogue.peak == round(float(factor.max()), 4)


def test_raw_profiles_keep_the_same_window_and_resolution(profiles):
    _, factor = profiles
    x, values = simbench.profile_series(REF, ["H0"], "2016-01-02", 1, "hourly")

    assert len(x) == 24
    np.testing.assert_allclose(
        values["H0"],
        np.round(factor[96:192].reshape(-1, 4).mean(axis=1), 4),
        atol=0.0001,
    )


def test_networks_without_profiles_still_have_static_power(profiles):
    network, _ = profiles
    network.profiles = {}

    assert simbench.profile_catalog(REF) == []
    x, power = simbench.element_power(REF, ["static"], "2016-01-01", 1)
    assert len(x) == 24 and power == {"static": [3.0] * 24}


def test_empty_catalogue_tables_are_skipped_but_network_records_are_kept(profiles):
    network, _ = profiles
    network.profiles["load"] = network.profiles["load"].iloc[:0]

    assert simbench.catalogue_profiles() == []
    record = simbench.profile_catalog(REF)[0]
    assert record.elements == 2 and np.isnan(record.mean) and np.isnan(record.peak)
