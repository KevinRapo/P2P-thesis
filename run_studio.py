"""Start the Studio on http://localhost:8090 with auto-reload (Run Python File in
VS Code works)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from studio.app import main  # noqa: E402

if __name__ in {"__main__", "__mp_main__"}:
    main()
