"""What the sanity scenarios are, as plain text.

The scenarios themselves run in ``environment/scenarios.py``; this is only what a
user interface needs to list them without loading the simulator.
"""

from __future__ import annotations

# id -> (title, what must happen)
INFO: dict[str, tuple[str, str]] = {
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
