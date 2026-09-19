# Commit history — `restore-baseline`

This is a chronological, per-commit narrative of every commit on this branch:
what changed, and why. It exists so a human (or a future AI session with no
memory of this work) can reconstruct the reasoning behind the current state
of the codebase without re-deriving it from the diffs alone.

This is a different lens than the other docs in this folder:
- **[`validation-fix-plan.md`](validation-fix-plan.md)** tracks defects by ID
  (P0–P3), independent of which commit fixed them.
- **[`methodology-baseline.md`](methodology-baseline.md)** is the current-state
  methodology description — what the baseline claims and why, as of now.
- **This file** is the development history — in what order things happened,
  and what each step actually did.

**Note on history rewrite (2026-09-18):** this branch's history was
reworked from an original 20-commit sequence built across two untracked
phases (2026-09-08/09, then 2026-09-13) into the 20 commits below. The
original sequence had a real problem: some things were fixed once and then
substantially rewritten later without ever landing as one clean commit —
most visibly the case6 notebook (touched 3 times, only the final version was
ever meant to be run) and four docs files (written once to describe an
earlier state, then rewritten to describe the later one). The rework
collapses those into single commits reflecting only the final, correct
state, while keeping genuinely distinct concerns that happened to touch the
same file (e.g. `src/agent/der.py`'s balance-sign fix vs. its later
perfect-foresight-leak fix) as separate commits, since those aren't
contradictions — they're two different bugs. Nothing was ever pushed to
`origin`, so this rewrite carries no external consequences; the original
sequence is preserved under the local branch `restore-baseline-pre-rework`
for anyone who wants the literal chronological record instead of this
cleaned-up one.

Every commit below is a real commit on `restore-baseline`; SHAs are the
first 7 hex characters, unique in this repo.

---

## Original restoration

**Context:** the goal was a correct, runnable copy of the *original* MARLEM
repository before starting separate SimBench integration work on top, since
neither the `marlem`/`validation` playground nor `marlem-main`/`main` were
fully working. Rather than re-deriving fixes from scratch, this phase ported
already-validated `src/` fixes from the `marlem-astra` worktree (proven there
against the full test suite and real notebook execution), then repaired each
of the 7 case notebooks and 2 example notebooks independently, then
documented and committed the result. Each `src/` commit was gated on a full
`pytest -q` pass before the next one started.

### `309bf7f` — fix: restore physical settlement kernel (agent/battery accounting)
Introduces `EnergySettlement`, a frozen per-step ledger recording generation,
demand, imports/exports, battery charge/discharge/loss, and
served/unserved/curtailed energy per agent — the foundation every downstream
reward, KPI, and conservation check reads from.
- `src/agent/der.py`: fixed a reversed balance sign (paper Eq. 13 defines
  `B = (G-D) + (bought-sold)`; the code computed `bought-sold` reversed, so
  buying created a deficit and selling created a surplus). Settlement now
  routes through the ledger instead of ad hoc per-call-site accounting.
- `src/agent/battery.py`: fixed charge/discharge boundary and efficiency
  equations to match Eq. 16, and allowed exact SoC bounds instead of
  rejecting them.

### `5a0615c` — fix: restore market mechanics (orders, pricing, matching, DSO, grid)
Depends on the settlement kernel above: immutable orders and fills now
reconcile against that ledger instead of being mutated in place during
matching.
- `src/market/order.py`: tracks submitted/remaining/filled quantities and
  source/delivered/loss separately instead of destructively decrementing
  `Order.quantity`, which had destroyed the audit trail reward/analytics code
  depended on.
- `src/market/mechanism.py`: gave every pricing mechanism one typed keyword
  signature. The matcher previously called all mechanisms positionally, so
  `SellerPricing`'s first positional parameter silently bound to the buyer's
  order (returning the buyer's bid instead of the seller's ask), and
  `BidAskSpreadPricing`'s third positional parameter received the market
  price instead of its blend factor.
- `src/market/matching.py`: uses the immutable order/fill model, routes DSO
  fallback through the same feasibility/settlement path as P2P trades
  instead of unconditionally clearing at zero distance/loss/fee, and
  preserves genuinely infeasible residual demand instead of discarding it.
- `src/market/dso.py`: requires feed-in tariff/utility price at construction
  (matches the class's own invariant); fixed fee calculation to use the
  immutable fill record.
- `src/grid/network.py`: resets per-period edge flow instead of letting it
  accumulate across an entire episode (a 24-step episode would otherwise
  progressively block later trades against capacity earlier, unrelated
  periods had already consumed); congestion now uses absolute flow so
  reverse flow doesn't report negative congestion.
- `src/grid/config.py`, `src/grid/base.py`: fixed the disconnected IEEE-34
  feeder (missing 832–888 edge) so the standard topology is one connected
  component.

### `2e6b881` — fix: restore environment core (action/observation/episode lifecycle)
- `src/environment/lem.py`: fixed an off-by-one episode termination (the
  terminal flag was checked before incrementing the step counter, so a
  configured N-step episode only ever executed N-1 transitions and never
  applied the terminal reward); replaced repeated global `np.random.seed`
  calls with per-component generators so resets no longer collapse distinct
  agents into identical profiles/reputations/balances.
- `src/environment/observation.py`: builds observations from the real
  step-0 state instead of hardcoding zeros at reset; stopped exposing exact
  future generation/demand sums to a decentralized policy that shouldn't
  have access to them.
- `src/environment/action.py`: kept the action space and its feasibility
  clamping aligned with what the market/physical state can actually accept.
- `src/profile/base.py`, `der.py`, `dso.py`: require `min_quantity`/
  `max_quantity` explicitly instead of silently defaulting; added
  `file_profile_mode` (`"price"` vs `"normalized"`) so a genuine measured
  price series replays unmodified while a bundled normalized-shape sample is
  honestly labeled and scaled via a seeded, documented procedure.

### `7592086` — fix: restore reward formula and implicit-cooperation KPIs
The "Level 2 implicit cooperation" mechanism central to the thesis's research
question; depends on the three commits above.
- `src/environment/reward.py`: fixed a duplicated weight name (`_w_local`
  was assigned `0.7` then silently reassigned to `0.3` a few lines later,
  discarding the first value); rebuilt the reward as the paper's structure
  (Eq. 3-6): weighted base term, market-wide cooperation factor, individual
  contribution factor, DSO/unmet-demand penalties, sign-preserving log
  compression.
- `src/coordination/implicit_cooperation.py`: computes the ten
  implicit-cooperation KPIs from the immutable settlement/trade records
  instead of proxies that didn't match their names (e.g. "social welfare"
  was plain transaction turnover). **Deliberate, user-approved deviation**:
  "social welfare" is now revealed bid/ask surplus, not the paper's literal
  turnover formula (turnover measures activity, not surplus). The reward's
  cooperation-bonus term also omits the paper's literal `-1` inside
  `max(0, f_coop·f_contrib - 1)`: with `f_coop`/`f_contrib` correctly
  normalized to [0,1], that product can never exceed 1, so the literal
  formula always evaluates to zero and silently disables the entire
  cooperation mechanism.
- `src/market/reputation.py`: guarded against a zero-weight configuration
  dividing by zero.

### `2dddc42` — fix: restore CTDE/CTCE learning infrastructure and inference parity
- `src/environment/ctde.py`: ensured the executed, decentralized actor heads
  are the same heads that receive the policy-gradient update (CTDE was
  training one set of heads and executing a different, untrained set);
  clamps each child distribution's own log-scale segment instead of the
  joint vector.
- `src/environment/ctce.py`: fixed the same class of Gaussian-stabilization
  bug for the joint distribution — clamping the joint vector in half instead
  of each child's own segment left one agent's log-scale unbounded while
  clamping another agent's mean.
- `src/environment/train.py`: uses one immutable agent order everywhere a
  grouped observation/action tuple is built or unpacked; fixed grouped
  reward reporting (RLlib's `GroupAgentsWrapper` already sums per-agent
  rewards — the code treated that sum as a mean and multiplied by agent
  count again, double-inflating the reported total); fixed training-config
  validation (the evaluation-duration predicate rejected every valid
  positive integer) and wrapped Ray's lifetime in try/finally so a failed
  run couldn't leave workers alive.
- `src/environment/inference.py`: restored the full RLlib `Algorithm` and
  its own action/distribution connectors for standalone inference, instead
  of hand-rolled Normal-distribution sampling that silently diverged from
  what the training-time connector pipeline actually produced.
- `src/environment/io.py`: preserves profile sources/seeds/columns and key
  ordering losslessly on save/restore instead of rounding values and
  dropping the metadata needed to reconstruct a scenario exactly.

### `e6e27bb` — test: add restoration invariant suite and fix legacy test/harness drift
- `tests/test_restoration_kernel.py` (new): the closest thing to a formal
  spec test — energy/cash conservation, battery dispatch accounting,
  network flow limits, profile/config isolation across environment
  instances, public cooperation signals, reward response to physical
  outcomes, preferred-partner allocation.
- `tests/conftest.py` (new): repo-root import fixture + a session-scoped
  `trained_case` fixture that trains one short real checkpoint per learning
  mode via `scripts/validate_learning.py`.
- Updated `test_checkpoint.py`, `test_inference.py`, `test_trainer.py`,
  `test_mechanism.py`, `test_profile.py`, `test_reward.py`,
  `test_implicit_cooperation.py`, `test_visualization.py` to match the
  corrected production signatures, replacing fixture-less functions pytest
  couldn't collect.
- `scripts/validate_learning.py` / `validate_notebooks.py` (new):
  short-real-checkpoint training-and-inference check, and headless notebook
  execution + figure/output verification.
- `environment.yml`: pinned `nbformat`/`nbclient` (this tooling's actual
  dependencies) and corrected a stale `networkx==3.4.2` pin to `3.6.1`.
- `.gitignore`: `downloads/` (RLTrainer's default storage path) was
  untracked-but-not-actually-ignored — only hidden locally via a
  non-shared `.git/info/exclude` rule. Added `downloads/*` +
  `!downloads/.gitkeep`.

**Gate:** `pytest -q` = 58 passed, 0 failed, 0 errors at this point.

### `0cad9e1` — fix: repair case1 market-mechanisms notebook execution
Confirmed broken as originally shipped, not introduced by this restoration:
`DERProfileHandler()` called with zero arguments in two places despite
`min_quantity`/`max_quantity` being required; a leftover pre-toggle cell
unconditionally ran 200-iteration real PPO training regardless of the
zero-intelligence toggle, plus a duplicate config cell; the
zero-intelligence loop used `if terminated or truncated:` on a
`MultiAgentDict` (always truthy — one step and done); results/plotting cells
referenced variables only populated by a later cell. Consolidated into one
correctly-ordered flow. Verified via the nbclient harness (`jupyter
nbconvert`'s PATH dispatch is unreliable on this machine).

### `debfc85` — fix: repair case2 agent-heterogeneity notebook execution
Same `DERProfileHandler` defect as case1, plus its own damage from apparent
ad hoc editing: a "CORRECTED" real-stepping cell sat *before* the cells
defining the variables it depended on (`NameError` before ever reaching its
own bug); a second "zero intelligence" cell fabricated rewards with
`random.uniform()` instead of stepping the environment at all; a third cell
was a redundant unconditional 200-iteration training loop; results-analysis
referenced undefined variables. Removed the fake/redundant cells, fixed the
loop condition, reordered results analysis after its dependencies.

### `c65c0cd` — fix: repair case3 DSO-intervention notebook execution
Same `DERProfileHandler`/loop-condition defects as case1/2, plus a duplicate
training cell, plus two defects specific to this notebook's premise
(comparing four DSO intervention strategies): the four `create_*_dso()`
helpers constructed `DSOAgent` without `feed_in_tariff`/`utility_price`
(rejected by the class's own constructor — true in the original repo too;
given a minimal placeholder, overwritten once profiles reset); and even once
constructed, the four strategy objects were never wired into the
environment (`DSOProfileHandler(dso_agent=...)` isn't a real parameter — all
four would have silently behaved identically). Now passed through
`scenario_config["dso"]`, the key the environment actually reads.

### `2dd8f0a` — fix: repair case4 grid-constraints notebook execution
Same `DERProfileHandler`, loop-condition, and duplicate-training-cell
defects as case1–3. No case4-specific defects found.

### `ffa90c8` — fix: repair case7 scalability-analysis notebook execution
Same `DERProfileHandler` defect as case1–4. Separately: `AGENT_POPULATIONS`
starts at 1, but `GridTopology.MESH` structurally requires ≥2 nodes — the
notebook's own hardcoded "quick test" cell already hit this independently
of the population sweep. Fixed with `num_nodes=max(num_agents, 2)` without
changing the actual agent count.

### `930a652` — fix: make examples/getting_started.ipynb genuinely executable
As shipped, the config cell hardcoded the original author's own machine
paths (`/Users/nasalazar/Documentos/GitHub/...`). Training/restore/
checkpoint cells were commented "uncomment to run," but the `RLInference`
construction and inference cells were *not* commented out — running
top-to-bottom would build a valid environment and then crash restoring a
checkpoint from a path that could never exist on any other machine. Added a
`TRAINING` toggle (default `True`, 3 real iterations) gating those sections,
with paths derived dynamically from the run that just completed.
`STORAGE_PATH` made repo-relative.

**Note:** `case5_battery_coordination.ipynb` needed no repair commit at this
point — it was never touched, no defects found (it's first touched later, by
`bea52cc`'s cross-cutting termination-check guard).

---

## Methodology hardening

**Context:** an independent audit of this baseline found real methodological
gaps in how the 9 training-mode × algorithm combinations were compared, and
in some accounting/seeding behavior: unequal cross-algorithm sample budgets
under a shared `training_iteration` stop criterion, DTDE's summed
multi-agent reward vs. CTCE/CTDE's mean reward being compared
apples-to-oranges, a perfect-foresight observation leak (remaining-demand/
supply observations summed the *real* future profile, not a forecast),
`env.set_seed()` being a silent no-op, unseeded `reset()` silently replaying
the same seed forever, and always-on blockchain proof-of-work overhead. The
commits below close most of those gaps.

### `bc5967b` — feat: add reproducible Case 6 scenario factory
New `src/scenario.py`: a proper, documented, paper-aligned factory
(`build_case6_agents`, `build_case6_config`,
`build_case6_evaluation_config`, `case6_seed_schedule`) replacing the
notebook-embedded ad hoc agent/config construction. Explicitly records the
paper→CSV profile-column mapping (the paper doesn't publish one, so this
mapping is now an auditable fact in the config rather than an implicit
choice); maps the paper's 8 named participants to specific IEEE-34 node IDs
and capacities from the results paper's table; defaults
`blockchain_difficulty=0` for training (with `=2` available for an
audit/paper-scale run); adds a genuinely separate, distinctly-seeded
`build_case6_evaluation_config()` — the first place `evaluation_env_config`
(an `RLTrainer` parameter that had existed but was never actually populated)
gets real held-out content.

### `d7e2364` — fix: harden environment accounting and seeded inference
- `src/environment/lem.py`: fixed `reset()` so unseeded resets no longer
  silently replay `self.seed` forever (previously every "unseeded" reset
  produced an *identical* episode; now it draws from the persisting RNG
  stream, and explicit `reset(seed=x)` gives an exact, call-history-
  independent replay). Fixed `set_seed()`, which called global
  `np.random.seed()` and had **zero effect** on the environment's own local
  `Generator` — a silent no-op. Added seeded, per-episode multiplicative
  forecast noise (`actual*(1+U[-max_error,max_error])`) as a new
  `forecast_generation_profile`/`forecast_demand_profile`, independent of
  the physical profiles used for settlement.
- `src/agent/der.py`: `get_remaining_demand`/`get_remaining_supply` used to
  sum the agent's **real** demand/generation profile — i.e. the policy
  observed exact future demand/supply for the rest of the episode, a
  perfect-foresight information leak into a supposedly partially-observable
  Dec-POMDP. Now sums the new noisy forecast profile instead; physical
  settlement itself is untouched. Initial `balance` at reset moved from
  unseeded global `np.random.uniform` to the agent's own seeded RNG.
- `src/market/validation.py` / `matching.py`: `Validator(difficulty=0)` now
  skips the SHA-256 nonce-search mining loop entirely (this is what makes
  `scenario.py`'s `blockchain_difficulty=0` default actually work);
  `verify_chain()` only checks proof-of-work when `difficulty>0`, always
  still checks hash/chain integrity.
- `src/environment/observation.py`: widened remaining-demand/supply
  observation bounds by `(1+forecast_error)` since noisy forecast values can
  now exceed the physical maxima the old bounds assumed.
- `src/environment/inference.py`: `RLInference.inference()` gained a native
  `seed_schedule: Optional[list[int]]` parameter for per-episode explicit
  seeding, and a redundant extra `env.reset()` on episode completion was
  removed.

### `7327717` — feat: make training protocol and metrics auditable
- New `extract_run_metrics()` helper (`src/environment/train.py`): reads
  reward/step/episode counters from either the flat result root or the
  nested `env_runners`/`evaluation`/`learners` paths RLlib uses across
  API-stack versions, and reports `comparison_reward = raw_reward /
  num_agents` for DTDE — normalizing DTDE's summed multi-agent episode
  return to a per-agent mean so it's directly comparable to CTCE/CTDE's
  already-mean reward. **This fixes the reported comparison metric, not the
  training objective** — `GroupedLEM.step()` still literally optimizes group
  mean reward for CTCE/CTDE, unchanged.
- New optional `env_steps` stopping budget on `RLTrainer`: when set, Tune's
  stop condition becomes a shared `num_env_steps_sampled_lifetime` target
  instead of `training_iteration` — a genuinely equal sample budget across
  PPO/APPO/SAC. `batch_mode="complete_episodes"` now applies uniformly to
  all three algorithms. **Deliberately opt-in**: the case6 sweep's default
  still uses `training_iteration`, preserving the original paper protocol.
- Held-out evaluation hardening: when `evaluation_env_config` isn't
  supplied, the trainer now deep-copies the training config but forces a
  distinct seed (`train_seed+10000`) and tags `evaluation_split="held_out"`.
  `get_best_results()` now tolerates a missing evaluation metric instead of
  crashing checkpoint selection on short smoke runs.
- New env vars `MARLEM_RAY_TEMP_DIR` (redirect Ray's temp/object store off
  synced folders like OneDrive) and `MARLEM_KEEP_RAY_ALIVE` (suppress
  `ray.shutdown()` between sequential `trainer.train()` calls within one
  process).
- New `docs/thesis/methodology-baseline.md`: the methodology description
  referenced throughout this doc.
- New `tests/test_methodology.py` (11 tests): locks in the case6 factory
  matching the paper table, forecast noise being seeded/bounded/
  reproducible and never mutating physical profiles, `_aggregate_group_reward`
  correctness, full-episode rollouts staying inside declared observation
  bounds under 3 seeds, `extract_run_metrics` fallback behavior, all 3
  algorithms accepting `env_steps` + `complete_episodes`, held-out eval
  being a genuinely distinct config, graceful checkpoint selection without
  an eval metric, and `Validator(difficulty=0)` still passing
  `verify_chain()`. Pytest count moves 58 → 69.

### `bea52cc` — fix: guard CTCE/CTDE termination check across case1-5 notebooks
`if terminated['__all__'] or truncated['__all__']:` crashed with `TypeError:
'bool' object is not subscriptable` under CTCE/CTDE, because
`GroupedLEM.step()` returns plain bools while DTDE's `LocalEnergyMarket.step()`
returns dicts. Fixed with a type-checking guard in all five notebooks
(case5's first-ever touch on this branch).

### `0b5bdd2` — fix: make examples/zero_to_hero.ipynb genuinely executable
Its `env_config` was missing `agents`/`grid_network`/`dso`/profile handlers
`LocalEnergyMarket` actually requires; a new `make_basic_config()` helper
builds the full component graph. Also fixed stale `observation_space`/
`action_space` attribute names (should be plural) and an
`all(terminated.values())` bug that wrongly included the `"__all__"`
sentinel itself.

New `notebooks/_run_nb.py`: an in-process `nbclient` executor, replacing
reliance on a `jupyter-nbconvert` console script that resolves to a broken
`.venv` on this machine and silently reports success after crashing at
import. `scripts/validate_notebooks.py`'s `MPLBACKEND` switched to
`module://matplotlib_inline.backend_inline` so headless validation captures
the same inline figures a Jupyter user would see. Was a documented,
deliberately-deferred gap from the original restoration's `930a652`.

### `aefa61f` — fix: make case6 notebook genuinely executable with the full 9-combination sweep
Checkpoint/experiment paths were hardcoded to the original author's own
historical training run (`lem_ctce_sac_06September1341`) — now derived live
from the run that just completed. The bundled tariff CSVs need
`file_profile_mode="normalized"` or `DSOAgent` rejects construction.

Formalizes the 9-combination sweep (`("ctce","ctde","dtde") ×
("ppo","appo","sac")`) the notebook's markdown always claimed but the code
never actually ran: per-combo try/except isolation, real elapsed-time
measurement, a JSON summary persisted after every combo, a training-time
heatmap and ranking chart. Wires in `extract_run_metrics()` for the
DTDE-normalized comparison reward; evaluates against
`build_case6_evaluation_config()`; exposes the sweep via `MODES`/`ALGORITHMS`
list variables instead of hardcoded tuples; replaces a fixed `time.sleep(8)`
inter-combo Ray cooldown with `MARLEM_KEEP_RAY_ALIVE`.

*(This commit consolidates what was originally three separate commits
layered on top of each other over several days — see the note at the top of
this file. Only this final state was ever meant to be run.)*

### `9fb3bf4` — perf: cache shortest-path lookups and drop numpy-scalar overhead in env.step()
`GridNetwork`'s topology/edge weights are fixed after construction, so the
shortest path between any two nodes never changes for the object's lifetime,
but `update_flow_from_trade`, `get_path_congestion`, `path_delivery_factor`,
`max_transfer`, and a duplicate `Location.distance_to` call between
`matching.py` and `dso.py` each independently recomputed it. Added a
`_shortest_path_cache` on `GridNetwork` feeding all 4 call sites, plus a
`path_length()` helper to dedupe the DSO fallback distance calc and thread
the already-computed distance from trade creation into fee calculation.
Also replaced `np.isfinite`/`np.clip` on plain floats in
`transmission_loss` (159k+ calls in a 20-episode case6 profile) with
`math.isfinite`/min-max — numerically identical, without numpy's dispatch
overhead.

Measured (case6 config, 8 agents, IEEE34, real profiles,
`blockchain_difficulty=2`, isolated from RLlib/Ray): 480 raw `env.step()`
calls, 9.961s → 7.320s, **~26.5% faster**. Blockchain proof-of-work mining
is now the dominant remaining cost (~54% of `env.step()` time) — deliberate,
literal paper-faithful behavior, not touched here.

### `2760f69` — docs: rewrite test, notebook, and validation guides to match the final restored repository
`docs/tests.md` described a completely phantom test suite that never
existed in `tests/`; `notebooks/README.md` referenced a nonexistent
`cases/` Python package — both pre-existing rot from the original repo.
Rewritten to accurately describe the real suite and the real 7 notebooks.
Adds `docs/thesis/validation-fix-plan.md` (P0–P3 defect tracker) and
`docs/thesis/training-benchmarks.md` (this machine's measured `RLTrainer`
timings), both referenced elsewhere but never actually written until now.

*(This describes the fully restored, methodology-hardened repository in one
pass — see the note at the top of this file for why the original two-pass
version of these docs was collapsed.)*

### `42a6f36` — docs: plan SimBench and NiceGUI integration

Reorganized the documentation using the ownership convention established in
the dev worktree: repository-facing material stays in `docs/`, the two MARLEM
papers live in `docs/paper/`, and thesis-authored methodology, validation,
history, synthesis, and planning live in `docs/thesis/`. Updated repository and
notebook references to the moved files.

Added a cross-worktree knowledge map after reviewing the documentation in
`marlem`, `marlem-main`, `marlem-dev`, `marlem-astra`, and this baseline. The
map records which architecture, validation, experiment, and prototype lessons
apply here without importing status claims from other branches.

Added the implementation plan for the SimBench and NiceGUI layers. The plan
separates economic trade transport from post-settlement physical-grid
assessment, derives nodal injections from the conserved household settlement,
starts SimBench in shadow mode, preserves the legacy graph as a comparator,
keeps Ray training in an owned worker process, and defines contracts, file
layout, tests, acceptance gates, and the first implementation tickets. No
runtime integration was included in this documentation commit.

---

## Open items not addressed by any commit above

- **`GroupedLEM`'s training objective is still group-mean reward for
  CTCE/CTDE vs. DTDE's summed multi-agent return** — `7327717` fixed the
  *reported comparison metric* (`extract_run_metrics`'s
  `comparison_reward`), not this underlying asymmetry in what each mode's
  policy actually optimizes. This remains a documented, deliberate
  difference between training paradigms, not a bug.
- **The case6 sweep's default stopping criterion is still
  `training_iteration`**, not the new `env_steps` sample-matched budget —
  by deliberate choice, to preserve the original paper's protocol. A
  sample-matched sensitivity run is possible (`env_steps` is wired and
  tested) but is not what the committed notebook runs by default.
- **`src/analytics/*.py`** (unsupported metric claims, only reachable via
  `examples/zero_to_hero.ipynb`) and **`src/market/validation.py`'s
  proof-of-work "blockchain"** (still literal, actively exercised by
  case1/2/4/5 via `blockchain_difficulty=2`, doesn't break anything, just
  overclaims) were both never touched by the restoration — documented as
  known gaps rather than silently carried forward.

## Uncommitted work in progress (not part of any commit above)

After `42a6f36`, the working tree still contains four intentionally excluded
groups:

- `notebooks/case6_implicit_cooperation.ipynb` contains an in-progress smoke
  run and roughly 123 MB of captured output. It must not be committed in this
  form; any useful source-cell changes need to be separated from generated
  output and reviewed independently.
- `src/environment/train.py` contains resource-configuration work that
  separates `num_env_runners`, Ray CPU capacity, and Tune trial concurrency,
  plus an `evaluation_duration="auto"` compatibility change. It has no focused
  regression coverage yet.
- `scripts/benchmark_resources.py` depends on that trainer API and remains an
  untracked benchmark experiment rather than a validated repository tool.
- `notebooks/salazar_*` and their PNGs are exploratory profile-analysis
  artifacts and have not been curated into a reproducible notebook workflow.

The complete pre-rework state remains available on the local branch
`restore-baseline-pre-rework` for cross-checking.
