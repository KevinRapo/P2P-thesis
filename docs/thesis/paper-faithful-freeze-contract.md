# Paper-faithful baseline freeze contract

## Purpose

This contract defines when repeated audits of the restored MARLEM baseline may
stop. The target is not byte-for-byte preservation of the upstream repository.
It is the smallest executable implementation that preserves the papers'
coherent market, physical, information, reward, and MARL concepts while fixing
contradictions that would invalidate those concepts.

Passing this contract supports the claim **paper-faithful corrected baseline**.
It does not by itself support **numerical reproduction of the published
results**. That stronger claim requires the unpublished Case 6 profile mapping
and scaling or equivalent author-provided experiment artifacts.

## Source priority

When sources disagree, use this order and record the decision:

1. Physical/accounting identities and executable behavioral invariants.
2. Explicit equations and experiment tables in the papers.
3. The coherent intent stated in the surrounding paper text.
4. The upstream GitHub implementation and notebook.
5. A minimal documented correction.

An upstream behavior is not preserved merely because it existed. A paper
formula is not copied literally when it is mathematically inactive,
dimensionally inconsistent, or contradicts the paper's stated objective.

## Frozen conceptual contract

### Environment and market

- One action is submitted per active DER per period.
- Feasibility uses physical demand, generation, battery state, and grid limits.
- Orders retain their submitted values; matching tracks residuals separately.
- Source and delivered energy remain distinct when network loss is present.
- Household settlement conserves energy; market settlement conserves cash.
- The episode executes exactly the configured number of periods.
- Explicit reset seeds replay exactly and unseeded resets advance a local RNG.

### Information architectures

- CTCE actors and critics may use the joint observation.
- CTDE actor heads use only their corresponding local observations; its critic
  may use joint observations and actions. The same actor heads are trained and
  executed.
- DTDE uses independent policy/module instances, local observations, and local
  rewards.
- Agent ordering is immutable across observations, actions, training, restore,
  and inference.

### Reward aggregation

- Each DER receives the paper-structured individual reward `R_i`.
- DTDE policy `i` optimizes only `R_i`.
- CTCE and CTDE optimize `mean_i(R_i)`. With a fixed population this is a
  constant rescaling of the paper's `sum_i(R_i)`, not a different objective.
- Cross-paradigm reports use mean per-agent return. Raw totals remain recorded.

### Behavioral reward requirements

- Executing no trade cannot earn cooperation or stability credit for inactivity.
- For otherwise equivalent outcomes, P2P service ranks above DSO service, DSO
  service ranks above unmet demand, and lower curtailment ranks above higher
  curtailment.
- Terminal deferred demand lowers return.
- Public cooperation KPIs can shape an individual reward only when the agent's
  contribution is represented.
- Price stability and convergence require observed market activity; zero volume
  is not treated as perfect coordination.

## Approved minimal deviations

- Group mean replaces group sum for CTCE/CTDE numerical scaling.
- Revealed bid/ask surplus replaces `sum(price * quantity)` labelled as social
  welfare; the literal expression is turnover.
- The normalized cooperation bonus is monotonic rather than containing the
  paper expression that reduces it to zero throughout its stated domain.
- The upstream no-trade guard is combined with, rather than returned before,
  physical and terminal penalties.
- Windows uses the supported local RLlib learner path where the Linux/NCCL
  learner path is unavailable.

These deviations must remain named in the methodology and run provenance.

## Numerical-reproduction blocker

The results paper specifies participant roles, capacities, batteries, nodes,
and plots, but not the CSV column mapping or profile scaling. The upstream
notebook uses a different set of participants/capacities plus random columns
and undocumented scale factors. The current deterministic reconstruction makes
all eight agents daily net consumers, contrary to the published solar and
parking provider roles.

Until this is resolved, training may validate software and learning behavior,
but it cannot be reported as a reproduction of the paper's Case 6 numbers.
Acceptable resolutions are:

1. author-provided profiles/configuration; or
2. a separately named, versioned reconstruction derived from Figure 1, with
   every mapping and scaling decision disclosed.

## Freeze gates

The corrected baseline may be frozen for extension work when all of the
following hold:

- the complete test suite passes;
- all nine algorithm/mode combinations update actor weights and restore their
  checkpoints;
- fixed no-order, random, direction-aware, and rule-based policies are recorded;
- no-order is not the reward-maximizing baseline;
- learned checkpoints are evaluated on physical outcomes as well as reward;
- PBT parameters remain within declared domains;
- the Tune driver materializes isolated per-trial records containing the
  authoritative trial ID and actual episode seed;
- at least three short independent-seed runs show finite losses/gradients for
  each algorithm before a paper-scale campaign is started; and
- the Case 6 data status is labelled either `reconstructed-unverified` or is
  replaced by a validated versioned mapping.

Once these gates pass, a new audit finding changes the frozen baseline only if
it demonstrates a violated invariant, a source contradiction not already
recorded, or failed reproducibility. A stylistic preference or an alternative
valid MARL design is not sufficient reason to reopen it.

### Current gate status (2026-09-19)

| Gate | Status |
|---|---|
| Complete test suite | Pass: 74 tests |
| Nine algorithm/mode actor-update, restore, and inference smokes | Pass |
| No-order exploit | Pass: active direction-aware policy scores higher |
| Physical metrics recorded for learned smoke checkpoints | Pass |
| Bounded PBT domains | Pass |
| Authoritative per-trial records and actual episode seeds | Pass |
| No-order, random, direction-aware, and rule-based seed matrix | Open: no-order and direction-aware checked only |
| Three independent seeds per algorithm/mode | Open |
| Case 6 data status | Pass: `reconstructed-unverified` |

The code-level contract is therefore green, but the baseline is not yet frozen
for empirical claims. The two open rows are finite experiment-protocol work;
they are not a reason to reopen settled market, reward, or MARL architecture
decisions unless they expose a failed invariant.

## Extension boundary

SimBench and NiceGUI may build against the frozen interfaces before numerical
paper reproduction is solved, provided that:

- the legacy grid remains a named backend;
- SimBench initially runs as post-settlement physical assessment;
- the UI labels the scenario and validation status accurately; and
- reward is never displayed as a substitute for served demand, curtailment,
  P2P share, DSO reliance, or constraint violations.
