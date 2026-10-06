"""The left navigation: the four pages of the Studio."""

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
        ],
    ),
    ("Run", [NavItem("step", "Step", "skip_next", "/step")]),
    (None, [NavItem("settings", "Settings", "settings", "/settings")]),
]
