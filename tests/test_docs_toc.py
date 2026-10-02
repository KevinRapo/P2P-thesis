"""The generated contents blocks in the thesis documents match their headings."""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_docs_contents_are_up_to_date():
    result = subprocess.run(
        [sys.executable, str(REPO / "docs_thesis" / "toc.py"), "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, (
        "Contents out of date; run python docs_thesis/toc.py\n" + result.stdout
    )
