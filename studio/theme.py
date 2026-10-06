"""Visual identity of MARLEM Studio: colour palette here, styles in static/studio.css."""

from pathlib import Path

from nicegui import ui

CSS_FILE = Path(__file__).parent / "static" / "studio.css"

PALETTE = {
    "primary": "#0F766E",  # teal: energy / grid
    "secondary": "#334155",  # slate: structure
    "accent": "#D97706",  # amber: generation / highlights
    "positive": "#15803D",
    "negative": "#B91C1C",
    "warning": "#CA8A04",
    "info": "#2563EB",
    "dark": "#0F172A",
}

# Categorical colours for charts (paradigms, algorithms, series)
SERIES = [
    "#0F766E",
    "#D97706",
    "#2563EB",
    "#9333EA",
    "#DC2626",
    "#0891B2",
    "#65A30D",
    "#DB2777",
]


def apply_theme() -> None:
    """Call once per page, before building the layout."""
    ui.colors(**PALETTE)
    ui.add_css(CSS_FILE)
