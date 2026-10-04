"""The network catalogue tables match the stored statistics (networks.json)."""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_network_catalogue_is_up_to_date():
    result = subprocess.run(
        [sys.executable, str(REPO / "docs_thesis" / "networks.py"), "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, (
        "Network catalogue out of date; run python docs_thesis/networks.py\n"
        + result.stdout
    )
