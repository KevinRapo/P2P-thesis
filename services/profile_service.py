"""ProfileService: SimBench profiles of a network and of the complete catalogue.

Read from the networks and SimBench's data set through the pandapower adapter:
the Inspect page's profile tables, plots and class overview.
"""

from __future__ import annotations

from grid import simbench as adapter
from grid.contract import NetworkRef
from services.models import ProfileClass, ProfileType, Series
from services.profile_classes import CLASSES, category, description


class ProfileService:
    """SimBench profiles: a network's, the complete catalogue, their classes."""

    SAMPLE_DATA = False

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
        return [
            ProfileType(
                code=r.name,
                category=category(r.name, r.table),
                description=description(category(r.name, r.table)),
                table=r.table,
                quantities=list(r.quantities),
                elements=r.elements,
                mean=r.mean,
                peak=r.peak,
            )
            for r in adapter.profile_catalog(source)
        ]

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

    # --- SimBench's whole catalogue ---------------------------------------------------
    def catalogue_types(self, scenario: int = 0) -> list[ProfileType]:
        """Every profile SimBench ships, independent of any network.

        Built: read from SimBench's complete data set. ``elements`` is 0, as no
        network is involved.

        Args:
            scenario: SimBench scenario (0 = today, 1 and 2 = future scenarios).
        """
        return [
            ProfileType(
                code=r.name,
                category=category(r.name, r.table),
                description=description(category(r.name, r.table)),
                table=r.table,
                quantities=list(r.quantities),
                elements=0,
                mean=r.mean,
                peak=r.peak,
            )
            for r in adapter.catalogue_profiles(scenario)
        ]

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
