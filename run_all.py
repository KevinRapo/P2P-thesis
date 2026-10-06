"""Start the dev servers, each in its own console window.

    python run_all.py            # all of them
    python run_all.py docs clean # only some of them

    docs     marlem-refactor  MkDocs live preview   http://127.0.0.1:8000
    studio   marlem-refactor  Studio                http://localhost:8080
    clean    marlem-clean     Studio                http://localhost:8090
    docs-clean  marlem-clean  MkDocs live preview   http://127.0.0.1:8001

Each server gets its own window, so its log stays readable, Ctrl+C there stops
only that server, and the Studios' auto-reload works. Close a window to stop it.
"""

import subprocess
import sys
from pathlib import Path

# The folder that holds the worktrees (marlem-clean, marlem-refactor, ...).
ROOT = Path(__file__).resolve().parents[1]
PYTHON = r"C:\Users\Kevin\miniconda3\envs\marlem\python.exe"

SERVERS = {
    "docs": (
        ROOT / "marlem-refactor",
        [PYTHON, "-m", "mkdocs", "serve", "-f", "docs_site/mkdocs.yml"],
    ),
    "studio": (ROOT / "marlem-refactor", [PYTHON, "src_thesis/run_studio.py"]),
    "clean": (ROOT / "marlem-clean", [PYTHON, "run_studio.py"]),
    "docs-clean": (
        ROOT / "marlem-clean",
        [PYTHON, "-m", "mkdocs", "serve", "-f", "docs_site/mkdocs.yml"],
    ),
}


def main(names: list[str]) -> None:
    """Start the named servers (all when none are named)."""
    unknown = [n for n in names if n not in SERVERS]
    if unknown:
        sys.exit(
            f"Unknown server(s): {', '.join(unknown)}. Choose from {list(SERVERS)}"
        )
    for name in names or SERVERS:
        folder, command = SERVERS[name]
        subprocess.Popen(
            ["cmd", "/k", f"title {name} && " + subprocess.list2cmdline(command)],
            cwd=folder,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        print(f"started {name:7} in {folder.name}")


if __name__ == "__main__":
    main(sys.argv[1:])
