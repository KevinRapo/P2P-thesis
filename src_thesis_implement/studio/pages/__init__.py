"""Page modules; importing this package registers every route."""

from . import (
    compare,
    design,
    grid,
    home,
    library,
    market,
    participants,
    results,
    runs,
    summary,
    validate,
)

__all__ = [
    "home",
    "grid",
    "participants",
    "market",
    "summary",
    "design",
    "validate",
    "runs",
    "results",
    "compare",
    "library",
]
