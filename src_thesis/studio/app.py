"""MARLEM Studio entry point.

Run with the `marlem` conda env from the repository root:

    python -m src_thesis.studio            # http://localhost:8080

The Studio is presentation only: every page calls application services
(`src_thesis.application`) and never imports MARLEM, grid adapters or Ray.
"""

import os

from nicegui import ui

from . import pages  # noqa: F401  (registers routes)


def main(port: int = 8080, show: bool = True) -> None:
    ui.run(
        title="MARLEM Studio",
        port=port,
        show=show,
        reload=False,
        favicon="⚡",
        storage_secret=os.environ.get("MARLEM_STUDIO_SECRET", "marlem-studio-local"),
        show_welcome_message=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
