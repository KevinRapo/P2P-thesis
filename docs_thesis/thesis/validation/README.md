# Validation of the original MARLEM

> Adopted 2026-09-27: this layout replaced the earlier `validation/` files (paper-vs-code, plan-by-level, validation-plan-fix) and the two validation files in `paper/`. §"Where the old content went" maps each old section to its new place.

<!-- BEGIN toc (python docs_thesis/toc.py) -->
## Contents

- [Files](#files)
- [Rules that keep the files in sync](#rules-that-keep-the-files-in-sync)
- [ID scheme](#id-scheme)
- [Legends](#legends)
- [Code markers](#code-markers)
- [Where the old content went](#where-the-old-content-went)
- [Adoption (2026-09-27)](#adoption-2026-09-27)

<!-- END toc -->

## Files

| File | Holds | Edit it when |
|---|---|---|
| [issues.md](issues.md) | **The issue register**: every issue's text, exact code lines, evidence, class, step and **status**. Also the paper-origin review, the impact on the published results, and the completeness check. | An issue is found, changes status, or its code moves |
| [methodology.md](methodology.md) | What the papers specify (loop, model, all equations) and, per section, how the original code implements each element. The **only** paper-vs-code comparison. | The comparison of a paper element changes |
| [plan.md](plan.md) | The **work order**: steps A0 → D3 with components, decisions to take first and acceptance tests. Fault maps, root-cause propagation, decision log, progress. | A step's scope or test changes; a decision is taken |
| [check_docs.py](check_docs.py) | Checks that the files agree with each other and with the code markers, and rebuilds the generated tables and diagrams | — |
| [evidence/](evidence/) | [issue_demos.py](evidence/issue_demos.py): one small experiment per issue (48 so far), expected vs actual, plus a showability tier for all 80. [issue_demos.ipynb](evidence/issue_demos.ipynb) renders them one by one; [test_issue_demos.py](evidence/test_issue_demos.py) runs them as strict-xfail acceptance tests. [trace_original_episode.py](evidence/trace_original_episode.py): the older one-episode trace behind T1–T13. | A demo is added, or an issue is fixed (move its ID to `FIXED` in the test file) |
| [marlem-keep-replace-audit.md](marlem-keep-replace-audit.md) | Rebuild or repair: function-by-function verdicts for a SimBench edition built on the papers' method, the grid coupling, and what happens to the 80 issues | The rebuild plan changes |
| [rl-testbench.md](rl-testbench.md) | Standalone RL validation plan: reference environments, paradigm contracts, learning evidence and path back to MARLEM | The RL benchmark design or acceptance gates change |
| [archive/validation-plan-fix.md](archive/validation-plan-fix.md) | The earlier audit (P0-01 … P3-03). Frozen, not kept in sync. | Never |

[↑ Contents](#contents)

## Rules that keep the files in sync

1. **One home per fact.** Issue text, code lines, evidence and status live only in [issues.md](issues.md). The other files cite `I-xx` (linked to its register row) and do not restate the issue.
2. **Status is edited in one place**: the register's Status column. The plan's per-step tables, the fault maps and the progress table are generated from it.
3. **Generated blocks are never edited by hand.** They sit between `<!-- BEGIN generated:NAME -->` and `<!-- END generated:NAME -->`. After changing the register, run:

   ```text
   python docs_thesis/thesis/validation/check_docs.py --write
   ```

   Without `--write` it only checks, and fails if a block is stale. Use the `marlem` conda env.

   The **Contents** block at the top of each document and the `↑ Contents` links under each section are generated too. After adding or renaming a `##` / `###` heading, run `python docs_thesis/toc.py` ([tests/test_docs_toc.py](../../../tests/test_docs_toc.py) fails while they are stale).
4. **Code links point at exact lines of the original code, frozen in git tag `marlem-annotated`**: MARLEM as published, plus the issue markers, just before the code was split into modules (2026-10-05). The links are GitHub URLs at that tag, so they stay correct whatever later commits move or rewrite (push the tag: `git push origin marlem-annotated`). Links to the platform code (`application/`, `kernel/`, `studio/`, the SimBench adapter) stay relative and follow that code. The original before any annotation is git tag `marlem-original`.
5. **Closing an issue deletes its code markers in the same commit.** `check_docs.py` fails if a closed issue still has a marker, or if a marker's tag or step disagrees with the register.

[↑ Contents](#contents)

## ID scheme

| ID | Meaning | Defined in |
|---|---|---|
| `I-01` … `I-80` | Issue. The only issue ID; used in docs, code markers, tests (`test_I12_…`) and commits (`fix(I-12): …`). | [issues.md](issues.md) |
| `A0` … `D3` | Validation step (stage A–D, ordered by [P1] Fig. 2 level) | [plan.md](plan.md) |
| `T1` … `T13` | Evidence fact reproduced by the trace script | [issues.md §1](issues.md#1-evidence) |
| `[P1]`, `[P2]` | The two papers. `P` with brackets means a paper, nothing else. | [methodology.md](methodology.md) |
| `P0-01` … `P3-03` | Old fix-plan IDs. Aliases only, in the register's Old ID column. | [issues.md §6](issues.md#6-old-fix-plan-ids) |
| `R1` … `R9` | Architecture roadmap phases (renamed from `P1`–`P9` on 2026-09-27 to free `P` for the papers) | [../architecture/README.md](../architecture/README.md) |

[↑ Contents](#contents)

## Legends

**Origin**: where an issue comes from. They are settled in this order, because a lower origin is meaningless until the one above it is:

| Origin | Question | If it fails |
|---|---|---|
| **Paper** | Is what the paper describes sound, complete and unambiguous? | Record a decision in the [plan's decision log](plan.md#7-decision-log). The paper is not the oracle for this item. |
| **Fidelity** | Does the code implement what the paper describes? | Implement the paper, or record a justified deviation. |
| **Code** | Where the paper is silent, is the code internally correct (conservation, interfaces, no silent failure)? | Fix it with a test. |

These are *not* the paper's Levels 0–2; the levels order the plan.

**Type and status marks**: used for issues and for the rows of the methodology tables:

| Mark | Meaning | Code marker |
|---|---|---|
| ✅ | Code matches the paper | — |
| ⚠️ | Code runs but differs from the paper (a choice or a simplification) | `# DEVIATION I-xx [step] …` (amber) |
| ❌ | Code contradicts the paper or its own documented intent. A defect. | `# FAULT I-xx [step] …` (red) |
| ❓ | The paper is silent or ambiguous, so it cannot be the oracle. A decision must be recorded. | `# DECIDE I-xx [step] …` (blue) |

**Status** (register only): `open` → `agreed` (plan and test agreed) → `fixed` / `decided` / `wontfix`.

**Evidence**: `T1`…`T13` = reproduced by the trace script; `C` = code reading only; `—` = judgment or taken from the earlier audit.

[↑ Contents](#contents)

## Code markers

Each issue location in `src_thesis/` has a one-line comment directly above it, e.g.

```python
# FAULT I-12 [A5] Orders are mutated in place, so the reward, KPIs and info see residual quantities (0), not submitted ones
buy_order.quantity -= (proposed_quantity - transmission_loss)
```

The Todo Tree extension colours these lines, marks them on the scrollbar, and lists them grouped by tag. Register code links point at the line below the marker at tag `marlem-annotated`; in the working code the markers move with their code. A marker is deleted when its issue is closed (the original markers stay in git tag `marlem-original`). An issue with several locations numbers its markers and points to the next one, e.g. `# FAULT I-12 [A5] (2/3; next marketplace/market/matching.py:368) …`; the last points back to the first. `check_docs.py --write` keeps the numbering and the next-location line numbers current after code edits; without `--write` it fails when they are stale.

[↑ Contents](#contents)

## Where the old content went

| Old file / section | Now |
|---|---|
| `validation/paper-vs-code.md` §0 legends | This README |
| §0 evidence table | [issues.md §1](issues.md#1-evidence) |
| §1 loop, §2 component contract | Merged into the "Implementation" tables of [methodology.md](methodology.md). Rows only in the contract were added there (I-11, I-22, I-40, I-56, I-60, I-70, I-74, I-76, unmatched orders, asynchronous orders). |
| §3 paper origin, §4 impact, §6 register, §7 completeness | [issues.md](issues.md) §3, §4, §2, §5. The register gained Class and Status columns; § now points to the methodology section. |
| §5 validation order | Dropped (it only pointed to the plan) |
| `validation/plan-by-level.md` | [plan.md](plan.md). Per-step issue tables are generated; the root-cause table became the propagation diagram; a decision log was added. |
| `paper/marlem-faults-by-level.md` §1–2 | [plan.md §2](plan.md#2-fault-map), generated from the register (counts are now open issues, one per issue per class) |
| its §3 per-class summary | The register's Class column + the generated fault map |
| its §4–7 per-function tables | Dropped: the register rows, the methodology tables and the Todo Tree view of the code markers cover them |
| `paper/marlem-methodology.md` | [methodology.md](methodology.md); the hand-counted totals are generated |
| `validation/validation-plan-fix.md` | [archive/](archive/validation-plan-fix.md), frozen |

[↑ Contents](#contents)

## Adoption (2026-09-27)

Done: this folder replaced `validation/`; `paper/marlem-faults-by-level.md` and the code-annotated `paper/marlem-methodology.md` were removed (merged here); the paper-only copy became `paper/marlem-methodology.md`; inbound links were repointed; [tests/test_validation_docs.py](../../../tests/test_validation_docs.py) runs `check_docs.py`, so a stale doc fails `pytest`.

Also done 2026-09-27: roadmap phases renamed `P1`–`P9` → `R1`–`R9`; the NetworkX validated release (old P2) retired.

[↑ Contents](#contents)
