"""Build the 2024 German price files from the day-ahead prices and DESTATIS.

    python config/data/build_de_2024.py            # uses de_day_ahead_2024.csv
    python config/data/build_de_2024.py download   # fetches it first

de_2024.json       utility and feed-in from the spot price
de_2024_flat.json  utility from the spot price, a flat feed-in tariff

A simulated day takes the prices of the 2024 day with the same weekday (2926 days
later): the files keep the simulated dates as keys, and the shift as date_shift. With
s = max(spot, 0), per kWh:

    utility = s + adder          adder = household price − mean spot
    feed_in = max(s − fee, 0)
"""

import csv
import json
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import fmean
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
SPOT_CSV = HERE / "de_day_ahead_2024.csv"
SOURCE = (
    "https://api.energy-charts.info/price?bzn=DE-LU&start=2024-01-01&end=2025-01-05"
)
# DESTATIS household price 2024, band 2,500 to 5,000 kWh a year, EUR/kWh: energy and
# supply, network charges, taxes and levies; each the mean of the two half-years
# (H1 16.75, 11.31, 11.45; H2 16.33, 11.64, 11.47 ct/kWh; press releases PD24_375
# and PD25_123). The two parts of 0.1147 are 11.475 and 11.46 rounded.
HOUSEHOLD_PRICE = 0.1654 + 0.1147 + 0.1147
MARKETING_FEE = 0.004  # the direct marketer's fee on sold energy (assumed)
FLAT_FEED_IN = 0.08  # about the EEG rate for small rooftop PV in 2024
WEEKDAY_SHIFT = 2926  # 2016-06-01 and 2024-06-05 are both Wednesdays
BERLIN = ZoneInfo("Europe/Berlin")


def download() -> None:
    """Save the hourly day-ahead prices (EUR/MWh) with their local time."""
    request = urllib.request.Request(SOURCE, headers={"User-Agent": "thesis-analysis"})
    data = json.load(urllib.request.urlopen(request, timeout=120))

    with SPOT_CSV.open("w", newline="", encoding="utf-8") as file:
        out = csv.writer(file)
        out.writerow(["time", "eur_per_mwh"])
        for second, price in zip(data["unix_seconds"], data["price"]):
            if price is not None:
                when = datetime.fromtimestamp(second, BERLIN)
                out.writerow([when.isoformat(), price])


def read_days() -> dict[str, list[float]]:
    """Each day's 24 hourly prices per kWh. A clock-change day repeats or averages
    an hour to keep 24; the source's quarter-hours, if any, are averaged."""
    hours: dict[str, dict[int, list[float]]] = {}

    with SPOT_CSV.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            when = datetime.fromisoformat(row["time"])
            day = hours.setdefault(when.date().isoformat(), {})
            day.setdefault(when.hour, []).append(float(row["eur_per_mwh"]) / 1000)

    days = {}

    for name, day in hours.items():
        series = [fmean(day[h]) if h in day else None for h in range(24)]
        days[name] = [
            value if value is not None else series[h - 1]
            for h, value in enumerate(series)
        ]

    return days


def tariffs(spot: list[float], adder: float, flat: bool) -> dict[str, list[float]]:
    floored = [max(price, 0.0) for price in spot]
    sold = [max(s - MARKETING_FEE, 0.0) for s in floored]

    return {
        "utility": [round(s + adder, 4) for s in floored],
        "feed_in": [FLAT_FEED_IN] * 24 if flat else [round(s, 4) for s in sold],
    }


def write(name: str, days: dict[str, list[float]], adder: float, flat: bool) -> None:
    out = {}
    simulated = date(2016, 1, 1)

    while simulated.year == 2016:
        source = (simulated + timedelta(WEEKDAY_SHIFT)).isoformat()
        out[simulated.isoformat()] = tariffs(days[source], adder, flat)
        simulated += timedelta(1)

    mean = {
        kind: [round(fmean(d[kind][h] for d in out.values()), 4) for h in range(24)]
        for kind in ("utility", "feed_in")
    }
    feed_in = f"a flat {FLAT_FEED_IN}" if flat else f"max(s - {MARKETING_FEE}, 0)"
    description = (
        "German day-ahead prices of 2024 (Energy-Charts, DE-LU) as a dynamic household "
        "tariff, per kWh, one price per hourly market step from 00:00. Each day of "
        f"2016 takes the 2024 day {WEEKDAY_SHIFT} days later, the same weekday. With "
        f"s = max(spot, 0): utility = s + {adder:.4f} (DESTATIS 2024 household price "
        f"{HOUSEHOLD_PRICE:.4f} minus the mean spot), feed-in = {feed_in}. 'utility' "
        "and 'feed_in' at the top are the mean day; 'days' is what the market trades "
        "at. Built by build_de_2024.py."
    )
    head = {"description": description, "date_shift": WEEKDAY_SHIFT}
    text = json.dumps(head | mean | {"days": out})
    (HERE / f"{name}.json").write_text(text, encoding="utf-8")
    print(name, "days", len(out))


def main() -> None:
    if "download" in sys.argv[1:]:
        download()

    days = read_days()
    in_2024 = [price for name, day in days.items() if name[:4] == "2024" for price in day]
    adder = round(HOUSEHOLD_PRICE - fmean(in_2024), 4)
    print(f"mean spot {fmean(in_2024):.4f}, adder {adder}")
    write("de_2024", days, adder, flat=False)
    write("de_2024_flat", days, adder, flat=True)


if __name__ == "__main__":
    main()
