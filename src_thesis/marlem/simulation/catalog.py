"""What a user interface lists: the scripted controllers and the sanity scenarios.

Plain data only (no simulator imports), so the Studio's services can show titles,
descriptions and parameters without loading the market or pandapower. The
controllers themselves are in ``controllers.py``, the scenarios in
``scenarios.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParamSpec:
    """One parameter of a controller.

    Attributes:
        label: Name shown in the UI.
        default: Value used when none is given.
        low: Smallest allowed value.
        high: Largest allowed value.
        help: One sentence explaining it.
    """

    label: str
    default: float
    low: float
    high: float
    help: str = ""


@dataclass(frozen=True)
class ControllerSpec:
    """What the UI needs to know about a controller.

    Attributes:
        name: Registry name.
        title: Short title.
        description: What it does, in a sentence or two.
        params: Parameters by name.
    """

    name: str
    title: str
    description: str
    params: dict[str, ParamSpec] = field(default_factory=dict)


CONTROLLERS: dict[str, ControllerSpec] = {
    "no_order": ControllerSpec(
        "no_order",
        "No orders",
        "Nobody trades: the market stays silent. The reference for what the "
        "network does on its own.",
    ),
    "random": ControllerSpec(
        "random",
        "Random orders",
        "Zero-intelligence agents: random price, quantity and side each step.",
    ),
    "net_position": ControllerSpec(
        "net_position",
        "Sell surplus, buy deficit",
        "Each agent sells the generation it does not need and buys the demand it "
        "cannot cover, at a price between the DSO's feed-in tariff and utility "
        "price.",
        {
            "aggressiveness": ParamSpec(
                "Aggressiveness",
                0.0,
                0.0,
                1.0,
                "0: trade at the midpoint of the DSO's prices; 1: ask the DSO's "
                "own prices (matches with anyone).",
            )
        },
    ),
}

# id -> (title, what must happen)
SCENARIOS: dict[str, tuple[str, str]] = {
    "idle_market": (
        "Own load only, nobody orders",
        "The market stays silent and the grid sees only what the participants "
        "themselves consume.",
    ),
    "export_at_noon": (
        "Everyone exports at noon",
        "Voltage rises at the participants' buses around noon, and rises most at "
        "the far end of the feeder.",
    ),
    "import_in_the_evening": (
        "Everyone imports in the evening",
        "Voltage falls at the participants' buses in the evening, and falls most "
        "at the far end of the feeder.",
    ),
}


def names() -> list[str]:
    """Names of all controllers."""
    return list(CONTROLLERS)
