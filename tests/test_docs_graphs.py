"""The generated file graphs in the architecture documents match the code."""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_docs_graphs_are_up_to_date():
    result = subprocess.run(
        [sys.executable, str(REPO / "docs_thesis" / "graphs.py"), "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, (
        "File graphs out of date; run python docs_thesis/graphs.py\n" + result.stdout
    )
