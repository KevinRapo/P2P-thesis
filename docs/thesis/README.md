# Thesis documentation index

This folder contains documentation created while restoring, validating, and
extending MARLEM for the thesis. It is intentionally separate from:

- the inherited repository documentation in `docs/`; and
- the MARLEM papers in `docs/paper/`.

The files here describe this worktree only. Documents from the other worktrees
were treated as design input, not as evidence that their code exists in
`marlem-baseline`.

## Start here

1. [Baseline knowledge map](baseline-knowledge-map.md) — current architecture,
   scientific contracts, known limits, and the disposition of useful material
   found in the other worktrees.
2. [Paper-faithful freeze contract](paper-faithful-freeze-contract.md) — the
   finite conceptual and behavioral gate for ending baseline re-audits.
3. [SimBench and NiceGUI implementation plan](simbench-nicegui-implementation-plan.md)
   — the implementation sequence, proposed contracts, source layout, tests,
   and acceptance gates.
4. [Baseline methodology](methodology-baseline.md) — what the restored baseline
   currently claims and how Case 6 is configured.
5. [Validation and fix record](validation-fix-plan.md) — defect-by-defect status
   and remaining validation gaps.

## Supporting records

- [Training benchmarks](training-benchmarks.md) records measured runtime costs
  and warns against treating the full 3 × 3 Case 6 matrix as a quick test.
- [Commit history](commit-history.md) explains how the restored baseline was
  assembled.
- [`../tests.md`](../tests.md) describes the executable test suite.
- [`../paper/marlem.pdf`](../paper/marlem.pdf) and
  [`../paper/marlem-results.pdf`](../paper/marlem-results.pdf) are the two
  source papers.

## Documentation ownership rule

Use the following placement rule for future files:

| Location | Owner and purpose |
|---|---|
| `docs/` | Documentation inherited from, or serving, the repository itself |
| `docs/paper/` | Published papers about MARLEM |
| `docs/thesis/` | Thesis-authored analysis, decisions, plans, validation records, and methodology |

Do not copy a status claim from another worktree without checking the baseline
source and tests. In particular, the `marlem` validation branch, `marlem-dev`,
and `marlem-astra` contain different model choices and different unfinished or
uncommitted work.
