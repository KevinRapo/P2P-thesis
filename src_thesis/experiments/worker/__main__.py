"""Run one run: ``python -m src_thesis.experiments.worker --run-dir <folder>``.

See ``process.main``.
"""

import sys

from src_thesis.experiments.worker.process import main

sys.exit(main())
