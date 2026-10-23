"""Atomic file writes shared by training and the runner."""

import json
import os
import time
from pathlib import Path
from typing import Callable


def replace_file(path: Path, write: Callable[[Path], None]) -> None:
    """Write beside ``path``, then replace it so readers never see half a file."""
    tmp = path.with_name(path.name + ".tmp")
    write(tmp)

    for attempt in range(20):  # Windows refuses while a reader has the file open
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)


def write_json(path: Path, data: dict) -> None:
    """Replace a JSON file in one step, using the run files' existing format."""
    text = json.dumps(data, indent=2, default=str)
    replace_file(path, lambda tmp: tmp.write_text(text, encoding="utf-8"))
