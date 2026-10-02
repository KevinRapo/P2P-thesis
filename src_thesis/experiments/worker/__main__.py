"""Run one run: ``python -m src_thesis.experiments.worker --run-dir <folder>``.

See ``process.main``.
"""

import sys

from .process import main

sys.exit(main())
