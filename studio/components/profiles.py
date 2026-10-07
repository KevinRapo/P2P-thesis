"""Overview of SimBench's profile classes, after SimBench's own figure.

SimBench groups its time series into load (accumulated standard profiles and
individual devices), generation, storage and aggregated grids (Meinecke et al.,
2020, Figure 1). The overview draws these groups as panels with one tile per
class and its number of profiles, so the catalogue is clustered before it is
listed. Clicking a tile adds its class to the selection, clicking it again
removes it; the table lists the profiles of all selected classes.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Awaitable, Callable

from nicegui import ui

from studio.adapters.models import ProfileClass, ProfileType

# --------------------------------------------------------------------------------------
# Colours and captions
# --------------------------------------------------------------------------------------
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
    "Click classes to list only their profiles; several can be selected at once. "
    "Click a selected class again to remove it, or All / Clear selection to start "
    "over. Grouped as in SimBench's own overview of its time series (Meinecke et "
    "al., 2020)."
)


# --------------------------------------------------------------------------------------
# ProfileOverview: the class tiles
# --------------------------------------------------------------------------------------
class ProfileOverview:
    """SimBench's profile classes as panels of tiles, with a count per class.

    Tiles toggle: every clicked class stays selected until it is clicked again or
    the selection is cleared.

    Args:
        classes: The classes, in display order (``profiles.profile_classes``).
        on_pick: Called with the selected class keys (empty: all profiles).
    """

    def __init__(
        self,
        classes: list[ProfileClass],
        on_pick: Callable[[set[str]], Awaitable[None]],
    ) -> None:
        self.classes = classes
        self.on_pick = on_pick
        self.picked: set[str] = set()
        self.counts: Counter[str] = Counter()
        self.box = ui.column().classes("w-full gap-2")
        with ui.row().classes("w-full items-start no-wrap gap-3"):
            self.hint = ui.column().classes("grow gap-0")
            self.clear = (
                ui.button(
                    "Clear selection",
                    icon="clear_all",
                    on_click=lambda: self.pick(None),
                )
                .props("flat dense no-caps")
                .classes("shrink-0")
            )
        self._explain()

    def show(self, types: list[ProfileType]) -> None:
        """Draw the panels with the number of ``types`` in each class."""
        self.counts = Counter(t.category for t in types)
        self._draw()

    def _draw(self) -> None:
        """(Re)draw all panels; the selected tiles are highlighted."""
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
                    "Every profile (clears the selection)",
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
        if (key in self.picked) if key else not self.picked:
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
        """Toggle a class in the selection (``None``: clear it); explain the
        selection and tell the owner.
        """
        if key is None:
            self.picked.clear()
        else:
            self.picked ^= {key}
        self._draw()
        self._explain()
        await self.on_pick(set(self.picked))

    def _explain(self) -> None:
        """One line per selected class: where it sits, its count, what it is."""
        self.hint.clear()
        self.clear.set_visibility(bool(self.picked))
        with self.hint:
            if not self.picked:
                ui.label(NO_PICK).classes("mls-card-caption")
                return
            chosen = [c for c in self.classes if c.key in self.picked]
            total = sum(self.counts[c.key] for c in chosen)
            ui.label(
                f"{total} profiles in {len(chosen)} "
                f"class{'es' if len(chosen) > 1 else ''}:"
            ).classes("text-body2 text-weight-medium")
            for c in chosen:
                where = " · ".join(p for p in (c.group, c.subgroup) if p)
                ui.label(
                    f"{c.name} ({where}), {self.counts[c.key]}: {c.description}"
                ).classes("mls-card-caption")
