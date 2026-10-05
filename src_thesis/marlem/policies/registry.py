"""The controllers by name: how an experiment file picks one.

``catalog`` is plain metadata (title, description, parameters) that the Studio
shows without loading any simulator code; ``get_policy`` builds one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src_thesis.marlem.core.policy import Policy
from src_thesis.marlem.policies.scripted import NetPosition, NoOrder, RandomOrders


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
class PolicySpec:
    """What the UI needs to know about a controller.

    Attributes:
        name: Registry name.
        title: Short title.
        description: What it does, in a sentence or two.
        params: Parameters by name.
        factory: Builds the policy from the parameters.
    """

    name: str
    title: str
    description: str
    factory: Any
    params: dict[str, ParamSpec] = field(default_factory=dict)


CATALOG: dict[str, PolicySpec] = {
    "no_order": PolicySpec(
        "no_order",
        "No orders",
        "Nobody trades: the market stays silent. The reference for what the "
        "network does on its own.",
        NoOrder,
    ),
    "random": PolicySpec(
        "random",
        "Random orders",
        "Zero-intelligence agents: random price, quantity and side each step.",
        RandomOrders,
    ),
    "net_position": PolicySpec(
        "net_position",
        "Sell surplus, buy deficit",
        "Each agent sells the generation it does not need and buys the demand it "
        "cannot cover, at a price between the DSO's feed-in tariff and utility "
        "price.",
        NetPosition,
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


def names() -> list[str]:
    """Names of all controllers."""
    return list(CATALOG)


def get_policy(name: str, **params: float) -> Policy:
    """Build a controller by name.

    Args:
        name: One of ``names()``.
        **params: Its parameters; unknown or out-of-range values are errors.

    Raises:
        ValueError: Unknown controller, unknown parameter or value out of range.
    """
    if name not in CATALOG:
        raise ValueError(f"Unknown controller {name!r}; use one of {names()}")
    spec = CATALOG[name]
    for key, value in params.items():
        if key not in spec.params:
            raise ValueError(f"{name} has no parameter {key!r}")
        p = spec.params[key]
        if not p.low <= value <= p.high:
            raise ValueError(f"{name}.{key} must be between {p.low} and {p.high}")
    return spec.factory(**params)
