"""Reproducible benchmark manifests.

Provenance (code commit, dirty state, package versions) comes from the
experiment layer's ``code_fingerprint`` and ``environment_fingerprint``, so
benchmark runs and market runs record it the same way. The benchmark keeps its
own manifest because it has no experiment file.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src_thesis.experiments.models.files import atomic_write_text
from src_thesis.experiments.models.manifest import (
    code_fingerprint,
    environment_fingerprint,
)

# Packages the benchmark depends on beyond the experiment layer's list.
BENCH_PACKAGES = ("pettingzoo", "mpe2")


def manifest(
    case_id: str, run: dict[str, Any], results: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Everything needed to rerun and judge one benchmark run.

    Args:
        case_id: The benchmark case.
        run: The run's settings: algorithm, paradigm, seeds, budget, the
            environment settings and the trainer's arguments.
        results: Evaluation results and the checkpoint path, once known.
    """
    environment = environment_fingerprint()
    environment["packages"].update(_versions(BENCH_PACKAGES))
    return {
        "kind": "rl-benchmark",
        "case": case_id,
        "created": datetime.now(timezone.utc).isoformat(),
        "run": run,
        "code": code_fingerprint(),
        "environment": environment,
        "results": results or {},
    }


def write_manifest(
    case_id: str,
    run: dict[str, Any],
    output_dir: Path,
    results: dict[str, Any] | None = None,
) -> Path:
    """Write ``manifest.json`` into ``output_dir`` (atomically); return its path."""
    path = Path(output_dir) / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(manifest(case_id, run, results), indent=1, default=str)
    return atomic_write_text(path, text + "\n")


def _versions(names: tuple[str, ...]) -> dict[str, str | None]:
    """Installed versions from package metadata; ``None`` if not installed."""
    from importlib import metadata

    out: dict[str, str | None] = {}
    for name in names:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    return out
