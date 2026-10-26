"""The left navigation: the pages of the Studio."""

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
    (
        "Build",
        [
            NavItem("inspect", "Inspect", "travel_explore", "/inspect"),
            NavItem("grid", "Grid & Participants", "hub", "/grid"),
            NavItem("market", "Market & DSO", "storefront", "/market"),
            NavItem("summary", "Summary", "fact_check", "/summary"),
        ],
    ),
    (
        "Validate",
        [
            NavItem("market_probes", "Market probes", "rule", "/market-probes"),
            NavItem("step", "Market step", "skip_next", "/step"),
            NavItem("rl_probes", "RL probes", "psychology", "/rl-probes"),
        ],
    ),
    (
        "Experiments",
        [
            NavItem("runs", "Runs", "insights", "/runs"),
            NavItem("results", "Results", "query_stats", "/results"),
        ],
    ),
    (None, [NavItem("settings", "Settings", "settings", "/settings")]),
]
