"""Overview of SimBench's profile classes, after SimBench's own figure.

SimBench groups its time series into load (accumulated standard profiles and
individual devices), generation, storage and aggregated grids (Meinecke et al.,
2020, Figure 1). The overview draws these groups as panels with one tile per
class and its number of profiles, so the catalogue is clustered before it is
listed. Clicking a tile picks the class.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Awaitable, Callable

from nicegui import ui

from src_thesis.application.models import ProfileClass, ProfileType

# Colour of each class, after the borders in SimBench's figure.
CLASS_COLOURS = {
    "household": "#E11D48",
    "commercial": "#2563EB",
    "agricultural": "#16A34A",
    "special_slp": "#7C3AED",
    "heat_pump": "#0F766E",
    "ev": "#DB2777",
    "pv": "#CA8A04",
    "wind": "#0284C7",
    "biomass": "#EA580C",
    "hydro": "#4F46E5",
    "power_plant": "#64748B",
    "storage": "#059669",
    "hv_grid": "#475569",
    "grid": "#334155",
    "exchange": "#94A3B8",
    "other": "#94A3B8",
}
GROUP_HINTS = {
    "Load": "Consumption",
    "Generation": "Feed-in",
    "Storage": "Charging and discharging",
    "Aggregated grids": "Whole grids as one element",
}
SUBGROUP_HINTS = {
    "Accumulated": "standard profiles for many customers",
    "Individual": "one device each",
}
NO_PICK = (
    "Click a class to list only its profiles; click it again, or All, to list "
    "every profile. Grouped as in SimBench's own overview of its time series "
    "(Meinecke et al., 2020)."
)


class ProfileOverview:
    """SimBench's profile classes as panels of tiles, with a count per class.

    Args:
        classes: The classes, in display order (``profiles.profile_classes``).
        on_pick: Called with the picked class key, or ``None`` for all profiles.
    """

    def __init__(
        self,
        classes: list[ProfileClass],
        on_pick: Callable[[str | None], Awaitable[None]],
    ) -> None:
        self.classes = classes
        self.on_pick = on_pick
        self.picked: str | None = None
        self.counts: Counter[str] = Counter()
        self.box = ui.column().classes("w-full gap-2")
        self.hint = ui.label(NO_PICK).classes("mls-card-caption")

    def show(self, types: list[ProfileType]) -> None:
        """Draw the panels with the number of ``types`` in each class."""
        self.counts = Counter(t.category for t in types)
        self._draw()

    def _draw(self) -> None:
        """(Re)draw all panels; the picked tile is highlighted."""
        self.box.clear()
        groups: dict[str, dict[str, list[ProfileClass]]] = {}
        for c in self.classes:
            groups.setdefault(c.group, {}).setdefault(c.subgroup, []).append(c)
        with self.box:
            with ui.row().classes("w-full gap-3 items-stretch"):
                self._tile(
                    "All",
                    sum(self.counts.values()),
                    None,
                    "Every profile",
                )
                for group, subgroups in groups.items():
                    self._group(group, subgroups)
            if self.counts.get("other"):
                ui.label(
                    f"{self.counts['other']} further profiles match no class; "
                    "they are listed under All with category 'other'."
                ).classes("mls-card-caption")

    def _group(self, group: str, subgroups: dict[str, list[ProfileClass]]) -> None:
        """One shaded panel: the group's name, then its (sub)groups of tiles."""
        with ui.column().classes("mls-pgroup gap-2"):
            with ui.column().classes("gap-0"):
                ui.label(group).classes("mls-pgroup-title")
                ui.label(GROUP_HINTS.get(group, "")).classes("mls-card-caption")
            with ui.row().classes("gap-3 no-wrap items-start"):
                for subgroup, classes in subgroups.items():
                    with ui.column().classes("gap-1"):
                        if subgroup:
                            ui.label(subgroup).classes("mls-psub-title").tooltip(
                                SUBGROUP_HINTS.get(subgroup, "")
                            )
                        with ui.row().classes("gap-2"):
                            for c in classes:
                                self._tile(c.label, self.counts[c.key], c.key, c.name)

    def _tile(self, label: str, count: int, key: str | None, name: str) -> None:
        """One clickable class tile: short label and number of profiles."""
        colour = CLASS_COLOURS.get(key or "", "var(--mls-muted)")
        classes = "mls-ptile"
        if key == self.picked:
            classes += " mls-ptile-active"
        if not count:
            classes += " mls-ptile-empty"
        with (
            ui.column()
            .classes(classes + " gap-0")
            .style(f"--c: {colour}")
            .tooltip(f"{name}: {count} profiles")
        ) as tile:
            ui.label(label).classes("mls-ptile-label")
            ui.label(str(count)).classes("mls-ptile-count")
        if count:
            tile.on("click", lambda key=key: self.pick(key))

    async def pick(self, key: str | None) -> None:
        """Pick a class (again: all profiles), explain it, tell the owner."""
        self.picked = None if key == self.picked else key
        self._draw()
        picked = next((c for c in self.classes if c.key == self.picked), None)
        if picked is None:
            self.hint.set_text(NO_PICK)
        else:
            where = " · ".join(p for p in (picked.group, picked.subgroup) if p)
            self.hint.set_text(
                f"{picked.name} ({where}), {self.counts[picked.key]} profiles: "
                f"{picked.description}"
            )
        await self.on_pick(self.picked)
