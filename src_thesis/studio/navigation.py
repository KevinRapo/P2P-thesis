"""Navigation structure, see docs_thesis/thesis/architecture/04-presentation.md §2–§3."""

from dataclasses import dataclass


@dataclass(frozen=True)
class NavItem:
    """One entry of the left navigation.

    Attributes:
        key: Matches ``shell(active=...)`` to highlight the current page.
        label: Text shown.
        icon: Material icon name.
        route: URL path.
    """

    key: str
    label: str
    icon: str
    route: str


NAV: list[tuple[str | None, list[NavItem]]] = [
    (None, [NavItem("home", "Home", "space_dashboard", "/")]),
    (
        "Build",
        [
            NavItem("grid", "Grid", "hub", "/build/grid"),
            NavItem("participants", "Participants", "groups", "/build/participants"),
            NavItem("market", "Market & DSO", "storefront", "/build/market"),
            NavItem("summary", "Summary", "fact_check", "/build/summary"),
        ],
    ),
    (
        "Experiment",
        [
            NavItem("design", "Design", "science", "/experiment/design"),
            NavItem("validate", "Validate", "rule", "/experiment/validate"),
        ],
    ),
    ("Run", [NavItem("runs", "Runs", "play_circle", "/runs")]),
    (
        "Analyse",
        [
            NavItem("results", "Results", "insights", "/results"),
            NavItem("compare", "Compare", "compare_arrows", "/compare"),
        ],
    ),
    (
        None,
        [
            NavItem("library", "Library", "folder_open", "/library"),
            NavItem("settings", "Settings", "settings", "/settings"),
        ],
    ),
]
