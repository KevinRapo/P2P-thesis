"""Command-line entry point for the standalone SimBench/pandapower proof."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from powerflow_demo import DEFAULT_SIMBENCH_CODE, run_demo


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load a SimBench LV feeder and compare three pandapower AC power flows."
    )
    parser.add_argument("--simbench-code", default=DEFAULT_SIMBENCH_CODE)
    parser.add_argument("--heavy-load-scale", type=float, default=2.0)
    parser.add_argument("--pv-kw", type=float, default=5.0)
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional path for machine-readable results; no MARLEM files are changed.",
    )
    args = parser.parse_args()

    results = run_demo(
        args.simbench_code,
        heavy_load_scale=args.heavy_load_scale,
        pv_kw=args.pv_kw,
    )
    print(f"SimBench network: {args.simbench_code}")
    print("pandapower AC power-flow results (power in kW, voltage in pu):")
    for result in results:
        print(
            f"  {result.scenario}: load={result.selected_load_kw:.3f}, "
            f"PV={result.added_pv_kw:.3f}, Vmin={result.min_voltage_pu:.5f}, "
            f"Vmax={result.max_voltage_pu:.5f}, "
            f"line_max={result.max_line_loading_percent:.2f}%, "
            f"trafo_max={result.max_transformer_loading_percent:.2f}%, "
            f"losses={result.total_losses_kw:.3f}, "
            f"external_grid={result.external_grid_p_kw:.3f}"
        )

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps([asdict(result) for result in results], indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {args.json_output}")


if __name__ == "__main__":
    main()
