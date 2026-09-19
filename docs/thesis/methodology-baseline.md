# MARLEM-restored baseline methodology

This repository uses the versioned label **MARLEM-restored baseline**. It is
an executable, internally tested reference implementation aligned with the
available MARLEM papers where details are published. It is not described as a
faithful reproduction because several paper details are underspecified and
the restored implementation makes explicit corrections.

## Case 6 reference scenario

The default Case 6 factory in `src/scenario.py` uses eight participants,
IEEE-34, total grid capacity 1800, average-price clearing, price bounds
20--600, quantity bounds 0.1--180, partner preferences, asynchronous orders,
and seed 42. Capacities, battery sizes, and node IDs are taken from the
results paper's participant table. Bundled generation and demand columns are
assigned deterministically to the eight participants (with distinct demand
columns where the source file contains duplicate archetypes). CSV values
are interpreted as normalized shapes and scaled by each participant capacity.
The paper does not publish a profile-column mapping, so this mapping is
recorded in the environment manifest rather than presented as a reproduction
of hidden source data.

The bundled data cannot currently reproduce the role mix shown in Figure 1 of
the results paper. With the deterministic mapping above, all eight participants
are net consumers over the day, including the solar farm and parking facility.
The upstream Case 6 notebook is not a missing source of truth: it randomly
selects columns, applies undocumented random scale factors, uses different
capacities, and does not instantiate the eight Table 6 participant roles.
Consequently, this factory is a **paper-parameterized reconstruction**, not the
published Case 6 data set. Numerical reproduction claims remain blocked until
the authors' profile mapping/scaling or an explicitly versioned reconstruction
of Figure 1 is available.

There is one source/config discrepancy worth making explicit: the original
Case 6 notebook selects `PROPORTIONAL_SURPLUS`, while the results paper's
case-study description selects average pricing (`(p_buy + p_sell) / 2`). The
restored factory follows the published case-study description (`AVERAGE`); the
original choice remains visible in the sibling repository for provenance.

Repository identifiers are normalized to `small_industry`, `hospital`,
`university`, `mall`, `residential`, `apartment`, `solar`, and `parking`; the
manifest also retains the paper labels (for example, `solar` means Community
Solar Farm). Table 8's initial algorithm settings are represented in the
scenario metadata and trainer: PPO/APPO learning rate 1e-5, gamma 0.99,
entropy coefficient 0.01, gradient clip 0.5, PPO clip 0.2 and minibatch 128,
APPO V-trace, and SAC actor/critic learning rates 1e-5 with dynamic entropy
and buffer capacity 1000. Smoke runs may override batch size and stopping
budget, and those overrides are recorded in the run manifest.

## Forecasts and evaluation

Physical generation and demand profiles are never perturbed. Observation-only
remaining supply and demand forecasts use independent, seeded, bounded
multiplicative errors `actual * (1 + U[-0.30, 0.30])` per time step. This is
the most reproducible interpretation of the paper's 30% forecast-error
statement. Explicit `reset(seed=x)` replays an episode; repeated unseeded
resets advance a local stream. Training and held-out evaluation configurations
use different seed bases, and inference supplies distinct held-out seeds.

## Reward and aggregation deviations

The environment reports both group total reward and group mean reward. The
centralized learner optimizes group mean reward. For the fixed eight-agent
scenario this is exactly the paper's summed CTCE/CTDE objective multiplied by
`1/8`: it does not change the optimum, but it avoids an architecture-dependent
gradient scale. DTDE policies still optimize their own individual rewards as
specified by Equation 19; only cross-paradigm reporting divides the aggregate
DTDE episode return by the agent count.

The restored reward keeps the upstream no-executed-trade guard, but unlike the
upstream early return it also applies physical unmet-demand and terminal
penalties. DSO reliance is scaled by the post-settlement grid imbalance as
described by Equation 3. This makes serving a deficit through the DSO preferable
to abandoning the demand, while P2P service retains the higher trading weight.
The resource KPIs follow the published P2P-share, P2P-flexibility, and recent
trading-volume convergence definitions. A deterministic regression requires an
active direction-aware Case 6 policy to score above the no-order policy.

The cooperation multiplier and welfare metric retain two explicit corrected
variants: a monotonic cooperation bonus replaces the paper's degenerate
normalized expression, and revealed bid/ask surplus replaces turnover labelled
as social welfare. These are deliberate corrections, not claims of literal
equation reproduction.

## Grid and units

The IEEE-34 graph is an abstract shortest-path congestion/loss simulator; it
does not perform AC or DC power-flow validation. The unit contract is kW for
power, kWh for hourly energy, currency/kWh for prices, and currency for cash.

## Training protocol

The implementation-comparison baseline uses the original repository's
stopping convention: `TRAINING_EPISODES` is passed directly to RLlib's
`training_iteration` stop condition. In the Case 6 notebook its default is
10,000. This preserves the original experiment protocol, but an RLlib
iteration is an algorithm-specific sample/update cycle, not necessarily one
24-hour episode and not necessarily the same number of environment steps for
PPO, APPO, and SAC. The run manifest records the requested iteration count;
result files also record sampled steps, episodes, and learner counters when
RLlib emits them.

The paper's Table 8 hyperparameters remain the initial settings: PPO/APPO
learning rate 1e-5, gamma 0.99, entropy coefficient 0.01, gradient clip 0.5,
PPO clip 0.2 and minibatch 128, APPO V-trace, and SAC actor/critic learning
rates 1e-5 with a capacity-1000 replay buffer. Their different batch/update
semantics are part of the algorithm comparison and are not silently replaced
with a common batch size. `env_steps` remains an explicit optional API for a
separate sample-matched sensitivity study, not the notebook's default.
The installed Ray release supplies the remaining algorithm defaults (PPO
rollout train batch 4,000, APPO train batch 500, SAC train batch 256 and its
replay warm-up threshold); these are reported in each run's Ray result/config
files rather than being mislabeled as paper hyperparameters.

When PBT is enabled, learning rates are resampled from `1e-6--1e-3`, entropy
coefficients from `1e-4--1e-1`, and GAE lambda from `0.8--0.99`. PBT always
resamples these declared domains instead of applying unbounded multiplicative
perturbations. This prevents the invalid `lambda > 1` configurations found in
the earlier saved runs while retaining the paper's initial values inside each
search range. After Tune returns, the driver materializes episode records from
Ray's result log inside each authoritative trial directory. The records include
the actual episode seed, and trials never append concurrently to one shared
JSONL file.

Smoke runs are execution checks only and are marked non-evidentiary. Final
claims require at least five independent seeds, train/validation/test
separation, held-out evaluation, confidence intervals, zero-intelligence or
fixed-rule comparators, cooperation/KPI ablations, and a small-instance
centralized optimization oracle where feasible. Proof-of-work mining is
disabled by default for training (`blockchain_difficulty=0`) while the hash
chain remains available for audit runs with difficulty 2.

On Windows the trainer uses RLlib's local learner (`num_learners=0`) because
the installed Windows Ray/PyTorch stack does not provide the Linux/NCCL worker
path used by the original repository (`num_learners=1`). This is a runtime
compatibility substitution; the algorithm hyperparameters and iteration stop
remain unchanged.

The paper describes 10,000 training episodes and a 24-step horizon (nominally
240,000 physical transitions), but the original code implements the first
number as Tune iterations. The baseline therefore reports both iteration and
sample counters rather than relabelling the iteration budget as an episode
budget. The notebook's default `TUNE_SAMPLES=1`, disabled periodic evaluation,
and local proof-of-work setting are deliberate run-time deviations from the
paper's 10-sample PBT/evaluation-heavy experiment; they are visible in the
manifest and can be changed for a literal paper-scale run. The original main
notebook contains `TUNE_SAMPLES=100`, which conflicts with the results paper's
published value of 10; the restored baseline follows the paper value when a
paper-scale population is requested.
