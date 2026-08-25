"""Run the standalone MARLEM Studio NiceGUI prototype."""

from nicegui import ui

from studio import ui as studio_ui  # noqa: F401 (page registration on import)


def main() -> None:
    ui.run(title="MARLEM Studio prototype", host="127.0.0.1", port=8081, reload=True)


if __name__ in {"__main__", "__mp_main__"}:
    main()
