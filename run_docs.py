"""Build or preview the documentation website locally (it is not published online).

    python run_docs.py              # live preview on http://127.0.0.1:8001
    python run_docs.py build        # check the site (--strict) and build it into site/
    python run_docs.py diagrams     # export the draw.io diagrams to SVG, then build

    serve      rebuilds on every change to docs/, the code and docs_site/
    build      fails on broken internal links and API documentation warnings
    diagrams   needed after editing a .drawio file (docs_site/export_drawio.py)

Run it from the marlem environment (``conda run -n marlem python run_docs.py``).
The source is docs/; docs_site/ only turns it into a website (docs/about.md).
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable
CONFIG = ["-f", "docs_site/mkdocs.yml"]

STEPS = {
    "serve": [[PYTHON, "-m", "mkdocs", "serve", *CONFIG, "--open"]],
    "build": [[PYTHON, "-m", "mkdocs", "build", *CONFIG, "--strict"]],
    "diagrams": [
        [PYTHON, "docs_site/export_drawio.py"],
        [PYTHON, "-m", "mkdocs", "build", *CONFIG, "--strict"],
    ],
}


def main(name: str) -> None:
    """Run the commands of one step in order, stopping at the first failure."""
    if name not in STEPS:
        sys.exit(f"Unknown step: {name}. Choose from: {', '.join(STEPS)}")
    for command in STEPS[name]:
        print(">", " ".join(command[1:]), flush=True)
        code = subprocess.call(command, cwd=ROOT)
        if code:
            sys.exit(code)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "serve")
