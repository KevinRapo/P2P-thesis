"""This machine's settings: the values that belong to a person or a site, not to the
project (the cluster account, SSH host, ports, folders).

They are read from, in this order:

1. the environment variable of the same name;
2. ``.env`` in the repository root (git-ignored; ``.env.example`` lists every key);
3. the default the caller gives.

``.env`` holds one ``KEY=VALUE`` per line; blank lines and lines starting with ``#``
are skipped, and quotes around a value are removed. ``hpc/hpc.ps1`` reads the
same file. Files such as ``hpc/targets.toml`` refer to a setting as ``${KEY}``, or
``${KEY:-default}`` with a default (``expand``).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parents[1]
ENV_FILE = REPO / ".env"

_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def read_env_file(path: Path = ENV_FILE) -> dict[str, str]:
    """The ``KEY=VALUE`` pairs of ``path`` (none when it does not exist)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}

    found = {}

    for line in text.splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, _, value = line.partition("=")
        value = value.strip()

        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]

        found[key.strip()] = value

    return found


def get(key: str, default: Optional[str] = None) -> Optional[str]:
    """The setting ``key``: the environment variable, else ``.env``, else
    ``default``. An empty value counts as not set."""
    value = os.environ.get(key) or read_env_file().get(key)
    return value or default


def expand(text: str, missing: Callable[[str], object]) -> object:
    """``text`` with each ``${KEY}`` or ``${KEY:-default}`` replaced by its setting.
    When a key without a default is not set, the result is ``missing(key)`` (the
    caller decides whether that is an error, and when)."""
    unset = []

    def value(match: re.Match) -> str:
        found = get(match.group(1), match.group(2))
        if found is None:
            unset.append(match.group(1))
            return ""
        return found

    expanded = _REFERENCE.sub(value, text)

    return missing(unset[0]) if unset else expanded
