"""The validation docs agree with each other and with the code markers.

Runs docs/thesis/validation/check_docs.py in check mode: broken links, unknown
issue IDs, stale generated tables or marker numbering, and markers that
disagree with the register fail the test. Fix with `check_docs.py --write`.
"""

import subprocess
import sys
from pathlib import Path

CHECK = Path(__file__).resolve().parents[1] / "docs/thesis/validation/check_docs.py"


def test_validation_docs_are_consistent() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECK)], capture_output=True, text=True, encoding="utf-8"
    )
    assert result.returncode == 0, result.stdout + result.stderr
