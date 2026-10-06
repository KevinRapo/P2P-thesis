"""Start MARLEM Studio: the one launcher.

    python src_thesis/run_studio.py        # http://localhost:8080

Works from any folder and from an editor's "Run Python File" button. It is the
same as ``python -m src_thesis.platform.studio``; settings (port, auto-reload,
browser tab) come from the environment or the repository's ``.env`` file, see
``platform/studio/app.py``.
"""

import runpy
import sys
from pathlib import Path

# Run as a plain script, Python puts this folder first on the import path, and
# src_thesis/platform would then shadow the standard library's ``platform``.
# Put the repository root there instead.
sys.path[0] = str(Path(__file__).resolve().parents[1])

runpy.run_module("src_thesis.platform.studio", run_name="__main__")
