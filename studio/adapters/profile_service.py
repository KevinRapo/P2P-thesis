"""ProfileService: SimBench profiles of a network and of the complete catalogue,
and the saved price files.

Read from the networks and SimBench's data set through the pandapower adapter:
the Inspect page's profile tables, plots and class overview.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import fmean
from typing import Any, Optional

from core.config.scenario import Scenario, price_files, read_prices
from core.grid import simbench as adapter
from core.grid.contract import NetworkRef
from studio.adapters.models import (
    DayElement,
    DayProfiles,
    ProfileClass,
    ProfileType,
    Series,
)
from studio.adapters.profile_classes import CLASSES, category, description


class ProfileService:
    """SimBench profiles: a network's, the complete catalogue, their classes."""

    # --- Classes ----------------------------------------------------------------------
    def profile_classes(self) -> list[ProfileClass]:
        """SimBench's profile classes, grouped as in SimBench's own overview.

        Built: a fixed list (load: accumulated and individual; generation;
        storage; aggregated grids). Every ``ProfileType.category`` is one of
        their keys, or ``"other"``.
        """
        return [profile_class for profile_class, _ in CLASSES]

    # --- A network's profiles ---------------------------------------------------------
    def profile_types(self, source: NetworkRef) -> list[ProfileType]:
        """The SimBench profiles a network ships, with how many elements use each.

        Built: read from the network through the pandapower adapter. Networks
        without profiles (pandapower built-ins) return an empty list.
        """
        return [_profile_type(r) for r in adapter.profile_catalog(source)]

    def profile_series(
        self,
        source: NetworkRef,
        codes: list[str],
        start: str,
        days: int = 7,
        resolution: str = "hourly",
        quantity: str = "p",
    ) -> Series:
        """Values of SimBench profiles over a time window, for inspection.

        Built: read from the network through the pandapower adapter.

        Args:
            source: The network whose profiles are read.
            codes: Profile names, as returned by ``profile_types``.
            start: First day (``YYYY-MM-DD``, in the profile year 2016).
            days: Length of the window in days.
            resolution: ``"15min"`` (raw), ``"hourly"`` or ``"daily"`` (means).
            quantity: ``"p"`` (active) or ``"q"`` (reactive; loads only).

        Returns:
            One y series per profile, as factors of the element's rated power.
        """
        x, y = adapter.profile_series(source, codes, start, days, resolution, quantity)
        return Series(
            x=x,
            y=y,
            x_label="time",
            y_label=f"{quantity} (factor of rated power)",
        )

    def profile_power(
        self,
        source: NetworkRef,
        codes: list[str],
        start: str,
        days: int = 7,
        resolution: str = "hourly",
        quantity: str = "p",
        per_element: bool = False,
    ) -> Series:
        """SimBench profiles scaled by the rated power of the elements using them.

        Built: each element's power is its profile factor times its rated power
        (SimBench's absolute values), summed per profile or shown per element.

        Args:
            source: The network.
            codes: Profile names, as returned by ``profile_types``.
            start: First day (``YYYY-MM-DD``, in the profile year 2016).
            days: Length of the window in days.
            resolution: ``"15min"`` (raw), ``"hourly"`` or ``"daily"`` (means).
            quantity: ``"p"`` (kW) or ``"q"`` (kvar; loads only).
            per_element: One series per element instead of one sum per profile.

        Returns:
            One y series per profile (e.g. "H0-A (6)": its six elements summed) or
            per element, in kW or kvar.
        """
        x, y = adapter.profile_power(
            source, codes, start, days, resolution, quantity, per_element
        )
        unit = "kW" if quantity == "p" else "kvar"

        return Series(x=x, y=y, x_label="time", y_label=f"{quantity} ({unit})")

    # --- The scenario's day -----------------------------------------------------------
    def day_profiles(self, scenario: Scenario) -> DayProfiles:
        """Every load, generator and storage unit of the scenario's network on its
        day, in kW per market step, each marked as a participant's or background.

        Built: SimBench's absolute profiles through the adapter, at the step length
        the market uses (hourly or 15 minutes).
        """
        g = scenario.grid
        ref = NetworkRef("simbench", g.code)
        owner = {e: p.id for p in scenario.participants for e in p.owns}
        elements = adapter.elements(ref)
        resolution = "hourly" if g.step_hours == 1.0 else "15min"
        x, power = adapter.element_power(
            ref, [e.id for e in elements], g.day, 1, resolution
        )

        return DayProfiles(
            x=x,
            step_hours=g.step_hours,
            elements=[
                DayElement(
                    id=e.id,
                    element_type=e.element_type,
                    bus=e.bus,
                    profile_type=e.profile_type,
                    owner=owner.get(e.id, ""),
                    kw=power.get(e.id, [0.0] * len(x)),
                )
                for e in elements
            ],
        )

    # --- SimBench's whole catalogue ---------------------------------------------------
    def catalogue_types(self, scenario: int = 0) -> list[ProfileType]:
        """Every profile SimBench ships, independent of any network.

        Built: read from SimBench's complete data set. ``elements`` is 0, as no
        network is involved.

        Args:
            scenario: SimBench scenario (0 = today, 1 and 2 = future scenarios).
        """
        return [_profile_type(r) for r in adapter.catalogue_profiles(scenario)]

    def catalogue_series(
        self,
        codes: list[str],
        start: str,
        days: int = 7,
        resolution: str = "hourly",
        quantity: str = "p",
        scenario: int = 0,
    ) -> Series:
        """Values of catalogue profiles over a time window, as factors of rated
        power.

        Built: read from SimBench's complete data set. Arguments as in
        ``profile_series``, without a network.
        """
        x, y = adapter.catalogue_series(
            codes, start, days, resolution, quantity, scenario
        )
        return Series(
            x=x,
            y=y,
            x_label="time",
            y_label=f"{quantity} (factor of rated power)",
        )

    # --- The price files --------------------------------------------------------------
    def price_files(self) -> list[str]:
        """The names of the saved price files (``config/data/``)."""
        return price_files()

    def price_dates(self, name: str) -> list[str]:
        """The dates a price file's prices are from, in order; empty if it holds one
        day."""
        return sorted(_dated_prices(read_prices(name)))

    def market_dates(self, name: str) -> list[str]:
        """The dates the market trades a price file's prices on, in the order of
        ``price_dates``."""
        return sorted(read_prices(name).get("days", {}))

    def price_series(
        self,
        name: str,
        start: Optional[str] = None,
        days: int = 1,
        resolution: str = "step",
    ) -> Series:
        """A price file's series, for inspection.

        Args:
            name: The file.
            start: First date (``YYYY-MM-DD``, one of ``price_dates``) of a file
                with dates; ``None``, or a file without dates: its one series over
                the day (with dates, that is the mean day, which the market does not
                trade at).
            days: Length of the window; it ends with the file's last date.
            resolution: ``"step"`` (one point per market step) or ``"daily"`` (the
                mean of each date).

        Returns:
            The utility price and the feed-in tariff per kWh.

        Raises:
            ValueError: ``start`` is not one of the file's dates.
        """
        prices = read_prices(name)
        dated = _dated_prices(prices)

        if start is None or not dated:
            x = _times_of_day(len(prices["utility"]))
            return _price_series(x, prices["utility"], prices["feed_in"], "time of day")

        if start not in dated:
            raise ValueError(f"The prices have no date {start}")

        first = date.fromisoformat(start)
        wanted = [(first + timedelta(i)).isoformat() for i in range(days)]
        found = {day: dated[day] for day in wanted if day in dated}

        if resolution == "daily":
            return _price_series(
                list(found),
                [fmean(series["utility"]) for series in found.values()],
                [fmean(series["feed_in"]) for series in found.values()],
                "date",
            )

        return _price_series(
            [
                f"{day} {time}"
                for day, series in found.items()
                for time in _times_of_day(len(series["utility"]))
            ],
            [price for series in found.values() for price in series["utility"]],
            [price for series in found.values() for price in series["feed_in"]],
            "time",
        )


def _dated_prices(prices: dict) -> dict[str, dict]:
    """A price file's ``days`` under the dates the prices are from: the market's date
    plus the file's ``date_shift``."""
    shift = timedelta(prices.get("date_shift", 0))

    return {
        (date.fromisoformat(day) + shift).isoformat(): series
        for day, series in prices.get("days", {}).items()
    }


def _times_of_day(steps: int) -> list[str]:
    """The start of each of a day's ``steps`` market steps, as HH:MM."""
    minutes = [step * 1440 // steps for step in range(steps)]

    return [f"{m // 60:02d}:{m % 60:02d}" for m in minutes]


def _price_series(x: list, utility: list, feed_in: list, x_label: str) -> Series:
    return Series(
        x=x,
        y={"Utility price": utility, "Feed-in tariff": feed_in},
        x_label=x_label,
        y_label="price per kWh",
    )


def _profile_type(record: Any) -> ProfileType:
    """A profile record of the grid adapter as the Studio shows it."""
    kind = category(record.name, record.table)
    return ProfileType(
        code=record.name,
        category=kind,
        description=description(kind),
        table=record.table,
        quantities=list(record.quantities),
        elements=record.elements,  # 0 in the catalogue: no network
        mean=record.mean,
        peak=record.peak,
    )
