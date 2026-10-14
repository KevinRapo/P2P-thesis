"""The Studio: pages to configure a market and step through it.

Start it with ``run_studio.py`` (VS Code: Run Python File, or the "Studio" launch
entry). Auto-reload is on: saving a .py file restarts the server and the open
browser tab reconnects with the new code. NiceGUI cannot reload a module started
with ``python -m``, so ``python -m studio.app`` runs without reload.
"""

from __future__ import annotations

import os
from pathlib import Path

from studio.adapters.workspace import default_home

# NiceGUI fixes its storage folder when it is imported: keep the per-browser state
# (dark mode) in the workspace, outside the repository and OneDrive.
os.environ.setdefault("NICEGUI_STORAGE_PATH", str(default_home() / "studio-state"))

from nicegui import app, ui  # noqa: E402

from studio.pages import (  # noqa: E402
    grid_participants,
    inspect,
    market_dso,
    runs,
    settings,
    step,
    summary,
)
from studio.state import services  # noqa: E402

# --------------------------------------------------------------------------------------
# Settings and routes
# --------------------------------------------------------------------------------------
# Port 8090, so it can run beside other local servers. MARLEM_CLEAN_PORT
# and MARLEM_CLEAN_SHOW=0 let a test run on its own port without opening a tab.
PORT = int(os.environ.get("MARLEM_CLEAN_PORT", "8090"))
SHOW = os.environ.get("MARLEM_CLEAN_SHOW", "1") == "1"
ROOT = Path(__file__).resolve().parents[1]

ROUTES = {
    "/inspect": inspect.page,
    "/grid": grid_participants.page,
    "/market": market_dso.page,
    "/summary": summary.page,
    "/step": step.page,
    "/runs": runs.page,
    "/settings": settings.page,
}


# --------------------------------------------------------------------------------------
# Start-up
# --------------------------------------------------------------------------------------
@app.on_startup
def _prepare_networks() -> None:
    """Prepare the LV and MV networks in the background, so the first time each
    is opened it reads from the cache."""
    services().grid.warm_cache(["LV", "MV"])


# --------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------
def main(reload: bool = True) -> None:
    """Register the pages and start the server.

    Args:
        reload: Restart the server when a .py file under the repository changes.
    """
    for path, build in ROUTES.items():
        ui.page(path)(build)
    ui.page("/")(lambda: ui.navigate.to("/inspect"))
    ui.run(
        title="MARLEM Studio",
        port=PORT,
        show=SHOW,
        reload=reload,
        uvicorn_reload_dirs=str(ROOT),
        uvicorn_reload_includes="*.py",
        favicon="⚡",
        storage_secret="marlem-studio-local",
        show_welcome_message=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main(reload=False)
