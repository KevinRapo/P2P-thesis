"""Regression test for deterministic measured-profile replay (P2-03)."""

import pandas as pd
import pytest

from src.profile.der import DERProfileHandler
from src.profile.dso import DSOProfileHandler


def test_csv_replay_preserves_selected_column_and_zero_values(tmp_path) -> None:
    generation_path = tmp_path / "generation.csv"
    demand_path = tmp_path / "demand.csv"
    pd.DataFrame({"house_a": [0.0, 1.25], "house_b": [8.0, 9.0]}).to_csv(generation_path, index=False)
    pd.DataFrame({"house_a": [2.5, 0.0], "house_b": [7.0, 6.0]}).to_csv(demand_path, index=False)
    handler = DERProfileHandler(1.0, 10.0, str(generation_path), str(demand_path), generation_column="house_a", demand_column="house_a")

    generation, demand = handler.get_energy_profiles(2, capacity=999.0)

    assert generation == [0.0, 1.25]
    assert demand == [2.5, 0.0]


def test_dso_csv_replay_preserves_selected_tariffs(tmp_path) -> None:
    feed_in_path = tmp_path / "feed_in.csv"
    utility_path = tmp_path / "utility.csv"
    pd.DataFrame({"tariff": [0.05, 0.17]}).to_csv(feed_in_path, index=False)
    pd.DataFrame({"tariff": [0.25, 0.37]}).to_csv(utility_path, index=False)
    handler = DSOProfileHandler(0.0, 1.0, str(feed_in_path), str(utility_path), feed_in_tariff_column="tariff", utility_price_column="tariff")

    feed_in, utility = handler.get_price_profiles(2)

    assert feed_in == [0.05, 0.17]
    assert utility == [0.25, 0.37]


def test_timestamped_replay_slices_a_named_regular_interval(tmp_path) -> None:
    path = tmp_path / "profile.csv"
    pd.DataFrame({"time": pd.date_range("2025-01-01", periods=4, freq="h"),
                  "energy": [0.0, 1.0, 2.0, 3.0]}).to_csv(path, index=False)
    handler = DERProfileHandler(0.0, 10.0, str(path), str(path),
                                generation_column="energy", demand_column="energy",
                                generation_timestamp_column="time", demand_timestamp_column="time",
                                replay_start="2025-01-01 01:00:00",
                                replay_end="2025-01-01 02:00:00",
                                expected_frequency="1h")

    generation, demand = handler.get_energy_profiles(2, capacity=1.0)

    assert generation == [1.0, 2.0]
    assert demand == [1.0, 2.0]


def test_timestamped_replay_rejects_irregular_cadence(tmp_path) -> None:
    path = tmp_path / "irregular.csv"
    pd.DataFrame({"time": ["2025-01-01T00:00:00", "2025-01-01T01:00:00", "2025-01-01T03:00:00"],
                  "energy": [0.0, 1.0, 2.0]}).to_csv(path, index=False)
    handler = DERProfileHandler(0.0, 10.0, str(path), generation_column="energy",
                                generation_timestamp_column="time", expected_frequency="1h")

    with pytest.raises(ValueError, match="frequency"):
        handler.get_energy_profiles(2, capacity=1.0)
