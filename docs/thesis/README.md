# Thesis documentation

```text
docs/
├── paper/                          # Source papers (the reference)
│   ├── marlem.pdf                  # [P1] MARLEM, Applied Energy 2026
│   ├── marlem-results.pdf          # [P2] Implicit-cooperation results (preprint)
│   ├── marlem-methodology.md       # Both papers' methodology + implementation status per section
│   ├── marlem-methodology copy.md  # Methodology without the implementation-status tables
│   └── marlem-faults-by-level.md   # Faulty modules per Fig. 2 level, with diagrams
└── thesis/
    ├── README.md                   # This index
    ├── validation/                 # Active work: validating the original MARLEM
    │   ├── plan-by-level.md        # Live plan and status tracker (start here)
    │   ├── paper-vs-code.md        # Contract: paper vs code, evidence, issue register
    │   ├── validation-plan-fix.md  # Earlier audit (P-IDs), reference only
    │   └── evidence/
    │       └── trace_original_episode.py   # Reproduces trace facts T1–T13
    └── architecture/               # Next: SimBench grid and the platform
        ├── README.md               # Master: goal, roadmap P1–P9, decision log (start here)
        ├── 01-paper-to-code-map.md # Fig. 2 → src_thesis, what changes
        ├── 02-simbench-grid.md     # Networks, profile assignment, grid contract, step changes
        ├── 03-experiment-config.md # Scenario / Experiment / Run specs, presets, sharing
        ├── 04-services.md          # Services, factory, worker, store, CLI
        └── 05-studio-ui.md         # NiceGUI shell and pages
```

## Validation (current focus)

| Document | Use it for |
|---|---|
| [validation/plan-by-level.md](validation/plan-by-level.md) | **What to do next.** Steps A0 → D3, ordered by [P1] Fig. 2 levels (Level 0 → Level 2 → Level 1). Holds each issue's **status** (the only place status is tracked). |
| [validation/paper-vs-code.md](validation/paper-vs-code.md) | **Why an issue exists.** What the paper says, what the code does, the trace evidence, and the full register I-01…I-80 with Origin (Paper / Fidelity / Code), Step and VP cross-reference. |
| [validation/validation-plan-fix.md](validation/validation-plan-fix.md) | Detailed evidence and fix rationale from the earlier audit. Looked up via the register's **VP** column. Its status fields are not maintained. |
| [validation/evidence/trace_original_episode.py](validation/evidence/trace_original_episode.py) | Rerunnable proof of the T1–T13 facts. Run with the `marlem` conda env: `python docs/thesis/validation/evidence/trace_original_episode.py` |

## Architecture (after validation)

Start with [architecture/README.md](architecture/README.md). It holds the goal, the roadmap (P1 = the validation above → P9 = evidence runs on SimBench), the decision log (D-01…) and the order to read the numbered documents 01–05.

`guidelines.md` and `tests.md` from the upstream repository were removed. See `marlem-main/docs/` for them.
