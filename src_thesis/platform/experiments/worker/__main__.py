"""Run one run: ``python -m src_thesis.platform.experiments.worker --run-dir <folder>``.

See ``process.main``.
"""

import sys

from src_thesis.platform.experiments.worker.process import main

sys.exit(main())
