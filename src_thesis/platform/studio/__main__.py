"""`python -m src_thesis.platform.studio`.

NiceGUI cannot auto-reload a package started with ``python -m``, so with
auto-reload on (the default) this runs ``app.py`` as a script instead; it makes
the repository importable itself. MARLEM_STUDIO_RELOAD=0 runs in-process.
"""

import os
import subprocess
import sys
from pathlib import Path

from src_thesis.platform.env import load_env

load_env()  # .env may switch auto-reload off

if os.environ.get("MARLEM_STUDIO_RELOAD", "1") == "1":
    app_file = Path(__file__).with_name("app.py")
    try:
        sys.exit(subprocess.call([sys.executable, str(app_file)]))
    except KeyboardInterrupt:
        sys.exit(0)

from src_thesis.platform.studio.app import main  # noqa: E402

main()
