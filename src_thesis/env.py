"""Settings from the repository's ``.env`` file.

``.env`` (git-ignored, copied from ``.env.example``) holds the MARLEM_* and
NICEGUI_* settings in one place. Variables already set in the environment win,
so a terminal or launch configuration can still override a value for one run.
Every setting has a default in the code that reads it; ``.env`` is optional.
"""

from __future__ import annotations

from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def load_env(path: Path = ENV_FILE) -> bool:
    """Load ``path`` into ``os.environ`` without overriding variables already set.

    Returns:
        True if the file exists and was read.
    """
    if not path.is_file():
        return False
    try:
        from dotenv import load_dotenv
    except ImportError:  # python-dotenv ships with NiceGUI; without it, skip
        return False
    return load_dotenv(path, override=False)
