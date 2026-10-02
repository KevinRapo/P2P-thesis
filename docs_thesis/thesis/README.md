# Thesis documentation

```text
docs/
├── paper/                          # Source papers (the reference)
│   ├── marlem.pdf                  # [P1] MARLEM, Applied Energy 2026
│   ├── marlem-results.pdf          # [P2] Implicit-cooperation results (preprint)
│   ├── marlem-methodology.md       # Both papers' methodology and equations (paper only, no code)
│   └── marlem-paper-to-code-map.md # Fig. 2 → the original code (src_thesis_reference), what changes
└── thesis/
    ├── README.md                   # This index
    ├── validation/                 # Active work: validating MARLEM against the papers
    │   ├── README.md               # Files, sync rules, ID scheme, legends, code markers (start here)
    │   ├── issues.md               # The issue register I-01…I-80: text, code lines, evidence, status
    │   ├── methodology.md          # The papers' method + how the original code implements each part
    │   ├── plan.md                 # Work order A0 → D3, fault maps, decision log, progress
    │   ├── marlem-keep-replace-audit.md # What to keep, rewrite or replace for a SimBench edition
    │   ├── check_docs.py           # Consistency checks; rebuilds the generated tables (--write)
    │   ├── archive/validation-plan-fix.md  # Earlier audit (P-IDs), frozen
    │   └── evidence/
    │       ├── issue_demos.py / .ipynb / test_issue_demos.py  # One demonstration per issue
    │       └── trace_original_episode.py   # Reproduces trace facts T1–T13
    └── architecture/               # Next: SimBench grid and the platform
        ├── README.md               # Master: goal, roadmap R1–R9, decision log (start here)
        ├── 01-simbench-grid.md     # Networks, profile assignment, grid contract, step changes
        ├── 02-experiment-config.md # Scenario / Experiment / Run specs, presets, sharing
        ├── 03-application-layer.md # Services: status, wiring, methods, returned data
        ├── 04-presentation.md      # NiceGUI Studio pages and the CLI
        ├── 05-experiment-layer.md  # experiments/: functions, store, worker, pool, run lifecycle
        └── implementation-status.md # what exists in code today and how to check it
```

## Validation (current focus)

| Document | Use it for |
|---|---|
| [validation/README.md](validation/README.md) | **Start here.** The files, the rules that keep them in sync, the ID scheme, the legends and the code-marker convention. |
| [validation/issues.md](validation/issues.md) | **Why an issue exists and where it stands.** The register I-01…I-80: text, exact code lines, class, step, evidence and **status** (the only place status is tracked). |
| [validation/methodology.md](validation/methodology.md) | **What the papers say vs what the code does**, section by section, with every equation. |
| [validation/plan.md](validation/plan.md) | **What to do next.** Steps A0 → D3 with acceptance tests, fault maps by level, the decision log and progress. |
| [validation/archive/validation-plan-fix.md](validation/archive/validation-plan-fix.md) | The earlier audit (P-IDs), frozen; its IDs map to issues in `issues.md` §6. |
| [validation/evidence/issue_demos.ipynb](validation/evidence/issue_demos.ipynb) | One small experiment per issue, expected vs actual; also runs as strict-xfail tests. |
| [validation/marlem-keep-replace-audit.md](validation/marlem-keep-replace-audit.md) | **Rebuild or repair?** Function-by-function verdicts (keep / keep + fix / rewrite / replace / drop / later RL) for building a SimBench edition on the papers' method, where the original is coupled to its grid, and what happens to the 80 issues. |
| [validation/evidence/trace_original_episode.py](validation/evidence/trace_original_episode.py) | Rerunnable proof of the T1–T13 facts. Run with the `marlem` conda env: `python docs_thesis/thesis/validation/evidence/trace_original_episode.py` |

## Architecture (SimBench edition)

Start with [architecture/README.md](architecture/README.md). It holds the goal, the roadmap (R1 = rebuild and validation above → R9 = evidence runs on SimBench), the decision log (D-01…) and the order to read the numbered documents 01–05.

`guidelines.md` and `tests.md` from the upstream repository were removed. See `marlem-main/docs/` for them.
