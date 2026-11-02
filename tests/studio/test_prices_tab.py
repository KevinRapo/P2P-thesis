"""The Inspect page's Prices tab: a window of a price file with dates."""

from __future__ import annotations

import csv
from datetime import date
from statistics import fmean
from types import SimpleNamespace

import pytest
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from core.config.scenario import PRICES_DIR, read_prices
from studio.adapters.profile_service import ProfileService
from studio.pages import inspect

PRICES = ProfileService()
FILE = "de_2024"
MARKET_DAY = "2016-06-15"
PRICE_DAY = inspect.PRICE_START  # what the market trades on MARKET_DAY


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_without_a_start_a_file_with_dates_shows_its_mean_day():
    series = PRICES.price_series(FILE)
    assert series.x[:2] == ["00:00", "01:00"] and len(series.x) == 24
    assert series.y["Utility price"] == read_prices(FILE)["utility"]


def test_a_window_holds_the_prices_of_its_dates():
    dated = read_prices(FILE)["days"]
    series = PRICES.price_series(FILE, PRICE_DAY, 2)
    assert len(series.x) == 48
    assert (series.x[0], series.x[24]) == ("2024-06-19 00:00", "2024-06-20 00:00")
    assert series.y["Utility price"] == (
        dated[MARKET_DAY]["utility"] + dated["2016-06-16"]["utility"]
    )
    assert series.y["Feed-in tariff"][:24] == dated[MARKET_DAY]["feed_in"]


def test_a_date_shows_the_spot_prices_of_that_date():
    with (PRICES_DIR / "de_day_ahead_2024.csv").open(encoding="utf-8") as file:
        rows = [row for row in csv.DictReader(file) if row["time"][:10] == PRICE_DAY]

    assert len(rows) == 24
    feed_in = PRICES.price_series(FILE, PRICE_DAY).y["Feed-in tariff"]
    for row, price in zip(rows, feed_in):
        assert price == pytest.approx(
            max(max(float(row["eur_per_mwh"]) / 1000, 0.0) - 0.004, 0.0), abs=1e-4
        )


def test_a_price_date_has_the_weekday_of_its_market_date():
    dates, market = PRICES.price_dates(FILE), PRICES.market_dates(FILE)
    assert (market[0], dates[0]) == ("2016-01-01", "2024-01-05")
    assert market[dates.index(PRICE_DAY)] == MARKET_DAY
    for ours, theirs in zip(dates, market):
        assert (
            date.fromisoformat(ours).weekday() == date.fromisoformat(theirs).weekday()
        )


def test_daily_shows_the_mean_of_each_date():
    day = read_prices(FILE)["days"][MARKET_DAY]
    series = PRICES.price_series(FILE, PRICE_DAY, 7, "daily")
    assert len(series.x) == 7 and series.x[0] == PRICE_DAY
    assert series.y["Utility price"][0] == pytest.approx(fmean(day["utility"]))


def test_a_window_ends_with_the_files_last_date():
    assert PRICES.price_dates(FILE)[-1] == "2025-01-04"
    assert len(PRICES.price_dates(FILE)) == 366
    assert len(PRICES.price_series(FILE, "2025-01-04", 7, "daily").x) == 1


def test_a_file_without_dates_has_its_one_day():
    assert PRICES.price_dates("synthetic_day") == []
    assert PRICES.market_dates("synthetic_day") == []
    assert len(PRICES.price_series("synthetic_day", PRICE_DAY, 7).x) == 24


@pytest.mark.parametrize("start", ["2024-06-", MARKET_DAY])
def test_a_start_outside_the_files_dates_says_so(start):
    with pytest.raises(ValueError):
        PRICES.price_series(FILE, start)


@pytest.mark.anyio
async def test_the_controls_change_the_window(monkeypatch):
    charts: list = []

    class Chart(inspect.PriceChart):
        def __init__(self, *args, **options):
            super().__init__(*args, **options)
            charts.append(self)

    monkeypatch.setattr(inspect, "PriceChart", Chart)

    def root() -> None:
        inspect._prices_tab(SimpleNamespace(profiles=PRICES))

    async with user_simulation(root) as user:
        await user.open("/")
        await user.should_see(
            "Prices of every date from 2024-01-05 to 2025-01-04. A market day trades "
            "at the date with its weekday: 2016-01-01 at 2024-01-05."
        )
        figure = charts[0].fig
        assert figure.data[0].x[0] == "2024-06-19 00:00"
        day = next(iter(user.find(kind=ui.input).elements))

        day.set_value("2024-02-")  # being typed
        await user.should_see(
            "The start day is a date from 2024-01-05 to 2025-01-04, written YYYY-MM-DD."
        )

        day.set_value("2024-02-03")
        assert charts[0].fig.data[0].x[0] == "2024-02-03 00:00"

        next(iter(user.find(marker="price-file").elements)).set_value("synthetic_day")
        await user.should_see("One day of prices, the same on every date.")
        assert charts[0].fig.data[0].x[0] == "00:00"
        assert not day.enabled
