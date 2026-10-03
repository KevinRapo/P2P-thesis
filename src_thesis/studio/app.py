"""MARLEM Studio entry point.

Run with the `marlem` conda env, either from the repository root:

    python -m src_thesis.studio            # http://localhost:8080

or by running this file directly (e.g. the "Run Python File" button in VS Code).
Settings come from environment variables, which can all be kept in the
repository's ``.env`` file (see ``.env.example``): MARLEM_STUDIO_PORT (default
8080), MARLEM_STUDIO_SHOW ("0" to not open a browser tab), MARLEM_STUDIO_RELOAD
("0" to switch off auto-reload), MARLEM_STUDIO_SECRET, MARLEM_STUDIO_GRID,
MARLEM_STUDIO_CONFIG, MARLEM_HOME, NICEGUI_STORAGE_PATH.

Auto-reload is on by default: saving a .py file under src_thesis/ restarts the
server process and the open browser tab reconnects with the new code. Services
are rebuilt on each reload, so the grid catalog loads its networks again.

The Studio is presentation only: every page calls application services
(`src_thesis.application`) and never imports MARLEM, grid adapters or Ray.
"""

import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    # Run as a plain script: make the repository root importable so the
    # package imports below resolve the same way as with `python -m`.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src_thesis.env import load_env  # noqa: E402

load_env()  # before anything reads MARLEM_* or NICEGUI_* settings

from src_thesis.application.workspace import default_home  # noqa: E402

# NiceGUI fixes its storage folder when it is imported: by default ".nicegui" in
# whatever directory Python was started from, so each start location got its own
# copy of the per-browser state. Keep it in the workspace instead, outside the
# repository and OneDrive. A value from .env or the environment still wins.
os.environ.setdefault("NICEGUI_STORAGE_PATH", str(default_home() / "studio-state"))

from nicegui import ui  # noqa: E402

# Importing a page module runs its @ui.page decorator, which registers the route.
import src_thesis.studio.pages.compare  # noqa: F401, E402
import src_thesis.studio.pages.design  # noqa: F401, E402
import src_thesis.studio.pages.grid  # noqa: F401, E402
import src_thesis.studio.pages.home  # noqa: F401, E402
import src_thesis.studio.pages.library  # noqa: F401, E402
import src_thesis.studio.pages.market  # noqa: F401, E402
import src_thesis.studio.pages.participants  # noqa: F401, E402
import src_thesis.studio.pages.results  # noqa: F401, E402
import src_thesis.studio.pages.runs  # noqa: F401, E402
import src_thesis.studio.pages.summary  # noqa: F401, E402
import src_thesis.studio.pages.validate  # noqa: F401, E402

SOURCE = Path(__file__).resolve().parents[1]  # src_thesis/


def main(
    port: int | None = None, show: bool | None = None, reload: bool | None = None
) -> None:
    """Start the Studio server.

    Args:
        port: Port; default ``MARLEM_STUDIO_PORT`` or 8080.
        show: Open a browser tab; default ``MARLEM_STUDIO_SHOW`` (on).
        reload: Restart on code changes; default ``MARLEM_STUDIO_RELOAD`` (on).
    """
    if port is None:
        port = int(os.environ.get("MARLEM_STUDIO_PORT", "8080"))
    if show is None:
        show = os.environ.get("MARLEM_STUDIO_SHOW", "1") == "1"
    if reload is None:
        reload = os.environ.get("MARLEM_STUDIO_RELOAD", "1") == "1"
    ui.run(
        title="MARLEM Studio",
        port=port,
        show=show,
        reload=reload,
        uvicorn_reload_dirs=str(SOURCE),
        uvicorn_reload_includes="*.py",
        favicon="⚡",
        storage_secret=os.environ.get("MARLEM_STUDIO_SECRET", "marlem-studio-local"),
        show_welcome_message=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
