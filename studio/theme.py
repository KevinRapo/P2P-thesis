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

# Colours with a meaning in charts: the same thing has the same colour on every page
MUTED = "#94A3B8"  # reference levels, empty buses, anything neutral
LIMIT = "#DC2626"  # limits and what breaks them (voltage band, violating buses)
HIGHLIGHT = "#D97706"  # marked buses (participants, the selected bus)

# Element types of a day's profiles
ENERGY = {"load": "#2563EB", "sgen": "#D97706", "storage": "#7C3AED"}

# Sides and counterparts of the market
MARKET = {"sell": "#D97706", "buy": "#2563EB", "p2p": "#15803D", "dso": "#64748B"}

# Bus kinds of the network plot (combined kinds fall back to their main element)
BUS = {
    "external_grid": "#0F172A",
    "load": "#0F766E",
    "pv": "#D97706",
    "load+pv": "#EA580C",
    "gen": "#B45309",
    "storage": "#7C3AED",
    "bus": "#94A3B8",
}


def apply_theme() -> None:
    """Call once per page, before building the layout."""
    ui.colors(**PALETTE)
    ui.add_css(CSS_FILE)
