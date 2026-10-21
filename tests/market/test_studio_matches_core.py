"""The Studio plays the same market as the core: validate_market.ipynb's scenario,
read the way the Studio reads it and stepped the way the Step page steps it, gives
the same day as ``LocalEnergyMarket`` called directly.

    python -m pytest tests            # or: python tests/test_studio_matches_core.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.config import store  # noqa: E402
from core.market.lem import LocalEnergyMarket  # noqa: E402
from studio.adapters.market_service import MarketService  # noqa: E402
from studio.adapters.scenario_service import ScenarioService  # noqa: E402

SCENARIO_FILE = ROOT / "config" / "scenarios" / "validate_market.json"


def test_studio_matches_core(tmp_path: Path) -> None:
    # The notebook's way: the file, then the whole day
    lem = LocalEnergyMarket(store.load(SCENARIO_FILE))
    lem.reset()
    expected = lem.run_to_end()

    # The Studio's way: the file as its current.json, then one click per part
    current = tmp_path / "scenarios" / "current.json"
    current.parent.mkdir(parents=True)
    shutil.copy(SCENARIO_FILE, current)
    market = MarketService()
    m = market.build(ScenarioService(current).current())
    while not m.done or m.pending is not None:
        market.next_part()

    assert len(m.history) == len(expected)
    for got, want in zip(m.history, expected):
        assert got == want, f"step {want.step} differs"


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        test_studio_matches_core(Path(folder))
    print("Studio and core give the same day.")
