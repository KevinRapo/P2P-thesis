# MARLEM validation and fix record — `marlem-baseline` (branch `restore-baseline`)

## Provenance

This document tracks the same defect catalogue as the original repository-wide audit (the `validation-fix-plan.md` that lives on the `marlem`/`validation` branch, itself dated 2026-08-08 against `main` at `04b6be1`), but describes what is **actually true in this worktree** — `marlem-baseline`, branched directly from `main`'s `15d6715`. This distinction matters: the `validation`-branch playground and this restoration made different implementation choices in places (most importantly, `validation` removed the partner-preference action component, the public KPI observation vector, and the paper's cooperation-shaped reward; this restoration kept all three, since preserving the paper's intended mechanisms was the explicit goal here — see `docs/guidelines.md` context and [[project-marlem-baseline-restoration]]). Do not assume a "Fixed" status on the `validation` branch's copy of this document describes this codebase.

Severity tiers (P0 correctness blocker / P1 model-validity blocker / P2 experimental-validity blocker / P3 maintenance-documentation defect) and issue numbering are kept identical to the original audit for cross-reference. Every "Fixed" item below was verified two ways: the full `pytest -q` suite (69 passed, 0 failed, 0 errors in the current environment, no restrictive `pytest.ini`) and, where the defect is notebook-visible, direct end-to-end execution of the affected notebook via an in-process `nbclient` harness (not `jupyter nbconvert` — see `docs/tests.md`). Commit references are on `restore-baseline`, range `b6f2548..e6c84a2`.

## P0 — correctness blockers

| # | Defect | Paper correspondence | Status in `marlem-baseline` |
|---|---|---|---|
| P0-01 | `DERAgent.update_battery_from_trades` computed `sold − bought` instead of `bought − sold` (reversed balance sign) | Eq. 13: `B = (G−D) + (bought−sold)` | **Fixed** (`b6f2548`) — routed through the new `EnergySettlement` ledger; balance sign matches the equation exactly |
| P0-02 | Buy/sell feasibility derived from the requested action, not physical surplus/deficit + battery availability | Eq. 15a–15d | **Fixed** (`b6f2548`) — feasibility now uses actual generation/demand/battery state |
| P0-03 | Direction/partner decisions didn't match the declared continuous action space; partner selection truncated a float inconsistently | Eq. 1–2 | **Fixed** (`5b6f774`) — action space and decoding aligned; partner preference (β) is preserved, not removed |
| P0-04 | Matching mutated submitted `Order.quantity` in place, destroying the audit trail before reward calculation | Algorithm 1, §3.9 | **Fixed** (`c1e99e6`) — orders are immutable; submitted/remaining/filled tracked separately |
| P0-05 | `SellerPricing`/`BidAskSpreadPricing` received the wrong positional arguments (seller pricing returned the buyer's bid) | §3.3.3, Eq. 9–11 | **Fixed** (`c1e99e6`) — one typed keyword interface for all six pricing mechanisms |
| P0-06 | Battery boundary/efficiency equations inconsistent; oversized requests rejected instead of clipped; exact SoC bounds rejected | Eq. 16 | **Fixed** (`b6f2548`) |
| P0-07 | Episode terminated after `N−1` transitions (terminal flag checked before step increment); terminal reward never applied | Algorithm 1, §3.9 phase 8 | **Fixed** (`5b6f774`) |
| P0-08 | Repeated global `np.random.seed` calls at reset made identically-configured agents collapse to identical profiles/reputations/balances | §3.4.4 | **Fixed** (`b6f2548`, `c1e99e6`) — per-component random generators |
| P0-09 | CTDE trained one set of actor heads and executed a different, untrained set | §3.7.1 | **Fixed** (`51c85b0`) |
| P0-10 | Grouped observations/actions could be assigned to the wrong agents (order inferred from a `set`) | Dec-POMDP formulation | **Fixed** (`51c85b0`) — one immutable agent order used everywhere |
| P0-11 | No conserved cash ledger; `DERAgent.profit` never updated | Eq. 14 | **Fixed** (`b6f2548`) — settlement ledger tracks buyer debit/seller credit |
| P0-12 | No functioning correctness test gate (fixture-less tests, drifted signatures, no CI) | — | **Fixed** (`292f5ad`) — full original `pytest -q`: 58 passed, 0 failed, 0 errors |

## P1 — model-validity blockers

| # | Defect | Paper correspondence | Status |
|---|---|---|---|
| P1-01 | Source/delivered/loss energy not conserved in settlement; buyer credited full pre-loss quantity | Eq. 18 | **Fixed** (`c1e99e6`) |
| P1-02 | Ordinary price-matched trades bypassed the network flow/capacity model entirely | §3.5.2–3.5.3 | **Fixed** (`c1e99e6`) |
| P1-03 | Grid flows accumulated across episode instead of resetting per period; unsigned; silently clipped | §3.5.3, Eq. 19 | **Fixed** (`c1e99e6`) — per-period reset, signed flow, `abs()` for congestion |
| P1-04 | IEEE34 feeder disconnected (missing `832–888` edge); impedance table unused | §3.5.1 | **Fixed** (`c1e99e6`) |
| P1-05 | DSO fallback bypassed grid feasibility; unmatched orders forcibly zeroed | §3.3.1, §3.5.2–3.5.3 | **Fixed** (`c1e99e6`) |
| P1-06 | Reward: duplicated `_w_local` weight (0.7 silently overwritten to 0.3); early returns skipped penalties; unnormalized KPI inputs | Eq. 3–6 | **Fixed** (`8db3875`) — see the two documented deviations below |
| P1-07 | Coordination KPIs didn't implement their names ("social welfare" = turnover; bid/ask lists reversed; etc.) | §3.6.2, Eq. 17–23 | **Fixed** (`8db3875`) — see deviation note on "social welfare" below |
| P1-08 | Analytics modules (`market_analytics.py`, `coordination_metrics.py`, `dso_metrics.py`, `grid_metrics.py`) report welfare/efficiency/fairness claims their inputs don't support | §3.6.2, §3.8 | **NOT ADDRESSED** — `src/analytics/` is byte-identical to `main`'s original, unmodified code. Confirmed via direct diff. Its only notebook consumer is `examples/zero_to_hero.ipynb`; that notebook now executes, but these metric definitions remain unverified. None of the 7 case-study notebooks or `examples/getting_started.ipynb` import this module. Flagging rather than silently carrying forward — treat any output from `src/analytics/*` as unverified until this is addressed. |
| P1-09 | Observations hardcoded zeros at reset; exposed exact future generation/demand sums to a decentralized policy | §3.2.1–3.2.2 | **Fixed** (`5b6f774`) |
| P1-10 | Reputation scores structurally degenerate (fragment-counted reliability, time-weight freezes updates) | Eq. 8, §3.3.4 | **Fixed** (`8db3875`) |
| P1-11 | Inconsistent units/timestep semantics across the system | §4.1 (context, not a full spec) | **Fixed** — `time_step_hours` threaded through battery power limits and profile conversion at environment construction boundaries (part of `b6f2548`/`5b6f774`) |
| P1-12 | CTCE described as a "theoretical upper bound" in the paper; an approximate learned policy isn't one | §3.7.1, §4.2 | **Partially a documentation claim, not purely code.** CTCE's Gaussian-clamping bug is fixed (`51c85b0`); the "upper bound" language is a thesis-writing note for whoever writes up results from this baseline — report CTCE as a centralized-information baseline, not a proven optimum, unless a small deterministic instance is separately solved exactly. |
| P1-13 | Preference matching and "clearing price" didn't define one coherent market design (reputation spliced into price-time sorting; heterogeneous settlement prices averaged into one number) | Algorithm 1, §3.3.2–3.3.4 | **Fixed** (`c1e99e6`) |

## P2 — experimental-validity blockers

| # | Defect | Status |
|---|---|---|
| P2-01 | Training evaluation not a held-out, independently-seeded protocol | **Partially addressed** — Case 6 now constructs a separate seed-10042 evaluation scenario and the trainer uses it when evaluation is enabled; multi-seed statistical reporting remains open. |
| P2-02 | Standalone inference didn't reproduce RLlib's action/information path | **Fixed** (`51c85b0`) — restores the full `Algorithm` and uses its own connectors |
| P2-03 | CSV "measured profiles" silently rescaled/noised/clipped instead of replayed | **Fixed** (`5b6f774`) — `file_profile_mode` distinguishes genuine replay from labeled, seeded normalization |
| P2-04 | Saved environment config couldn't reconstruct the original scenario (rounded profiles, dropped seeds/sources) | **Fixed** (`51c85b0`) |
| P2-05 | Training config validation defects (duration predicate, resource double-counting, unwrapped Ray lifetime) | **Fixed** (`51c85b0`) |
| P2-06 | No immutable experiment manifests/baselines/statistical reporting | **Partially addressed** — each training run writes an immutable environment/config manifest, source hashes, unit contract, and per-episode record file; independent-seed aggregation, confidence intervals, and fixed-rule/oracle baselines remain open. |

## P3 — maintenance/documentation defects

| # | Defect | Status |
|---|---|---|
| P3-01 | "Blockchain validator" claims decentralized consensus but is a single in-memory proof-of-work chain that omits distance/loss/fees from its hash | **NOT ADDRESSED** — `src/market/validation.py` remains a single in-memory proof-of-work/audit chain. Difficulty zero now skips mining while retaining integrity hashing for the Case 6 training path; difficulty 2 is still used by the other case notebooks. The implementation does not provide decentralized consensus, so its framing remains limited to validation/audit. |
| P3-02 | Defensive validation hides bad state or is internally ineffective (dead checks, bare `except`, mutable defaults) | **Substantially addressed incidentally** across the touched files during P0/P1 fixes; not independently re-audited as a standalone pass. |
| P3-03 | Documentation/notebooks describe a different repository state (phantom `cases/` package, wrong topology list, stale test inventory) | **Fixed** (`e6c84a2`) — `docs/tests.md` and `notebooks/README.md` rewritten to describe the actual 7 notebooks and actual test suite present in this worktree. |

## Two deliberate, approved deviations from literal paper text

Both in the reward/KPI layer (`8db3875`), both because the literal formula is degenerate or economically vacuous once other defects are fixed:

- **"Social welfare"** is implemented as revealed bid/ask surplus (`buy.price*delivered − sell.price*quantity − fees` on P2P trades), not the paper's literal `Σ price×quantity` turnover (results paper Eq. 4). The literal formula measures market activity, not surplus, and the original audit already flagged this as a paper-level conceptual issue (turnover mislabeled as surplus), not just an implementation bug.
- The reward's cooperation-bonus term (framework paper Eq. 4) omits the literal `−1` inside `max(0, f_coop·f_contrib − 1)`. With `f_coop` and `f_contrib` correctly normalized to `[0,1]` (as the paper specifies), that product can never exceed 1, so the literal formula always evaluates to zero and silently disables the entire cooperation mechanism — the mechanism the whole thesis is about. Dropping the `−1` preserves a working, monotonic bonus instead.

## Follow-up protocol corrections

The current `MARLEM-restored baseline` follow-up implements the previously
open reproducibility items in `docs/methodology-baseline.md`: explicit Case 6
scenario construction, normalized heterogeneous profile columns, seeded
bounded forecast errors, independent evaluation seeds, and an explicit
original-iteration training protocol with sampled-step diagnostics. The
historical statuses above describe the earlier restoration commits and are
retained as an audit trail.

- `src/analytics/*.py` (P1-08) — unmodified from `main`, unsupported metric claims still present. Only reachable via `examples/zero_to_hero.ipynb`.
- `src/market/validation.py` (P3-01) — still a single-process proof-of-work/audit chain; it is intentionally not presented as decentralized consensus.
- `examples/zero_to_hero.ipynb` — basic, full-day, and quickstart examples now construct explicit agents, grid, DSO, and profile handlers; the notebook passes the same direct `nbclient` execution gate as the other executable examples.
- `case6_implicit_cooperation.ipynb` now executes the documented 9-variant
  sweep (3 modes × 3 algorithms) using the original iteration stop. It still
  defaults to one Tune sample and disables per-iteration evaluation so a local
  reproduction remains operational; the paper's 10-sample PBT and evaluation
  cadence are documented deviations, not hidden settings.
- P2-01/P2-06's remaining full experimental-protocol apparatus (multiple independent seeds, confidence intervals, fixed-rule/oracle baselines) remains open; the held-out scenario and immutable run manifest are now implemented for reproducibility.
