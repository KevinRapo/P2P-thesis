# Finishing the RL layer: the plan

> Status: plan, 22 Oct 2026. Scope: V2 only, i.e. RLlib's PPO with the paper's
> mixed action ([P1] eq. 2) in CTCE, CTDE and DTDE on the market of
> `config/scenarios/validate_market.json`. It orders the work and names the
> decisions; it does not take them. Decisions go into the
> [decision log](decisions.md); how the pages fit together is in
> [Plans](index.md). It starts after the [market plan](market.md), which
> fixes what an agent can do, earn and know.

## Why a plan

The code exists end to end, and the probes and tests pass. What is missing is
evidence that PPO *learns the market* with the mixed action, and a recorded reason
for every choice that shapes what it learns. Without an order, each look at a
result raises a question in another layer and the work drifts. The plan fixes the
order so that each stage rests only on the stages before it.

**Rules for working through it**

1. **One stage at a time.** A stage is done when its *check* passes and its
   *decisions* are in the [decision log](decisions.md). Do not start the next one before.
2. **Parking lot.** A question that belongs to a later stage, or outside the RL
   layer, is written to the parking lot (end of this page) and left there.
3. **The market is frozen** after the [market plan](market.md). The RL work does
   not change the market's rules (`core/market/`). A market problem found here
   goes to the parking lot, unless it makes the stage's check impossible.
4. **Evidence before tuning.** No hyperparameter is changed to make a market curve
   look better before stage 4's diagnostics exist and stage 5 has shown what
   blocks learning.

## Overview

| # | Stage | Question it answers | Size | Status |
|---|---|---|---|---|
| 1 | The decision problem | Is the market, as the agents see it, the problem we mean? | M | not started |
| 2 | The learner on known answers | Does PPO with a mixed action learn what it should, in each paradigm? | M | done (26 Oct) |
| 3 | PPO design choices | Which settings follow from the method, before any tuning? | M | in progress (since 26 Oct): 3e, 3h decided |
| 4 | Diagnostics | What must a run report so that a failure can be explained? | S | mostly done (25 Oct): per-part statistics, KL, gradient norm, Learning tab; clip fraction open |
| 5 | First learning on the market | Does it learn the market, and which action part is the obstacle? | L | not started |
| 6 | Budget and hyperparameters | How long, and with which settings? | M | in progress (since 26 Oct): settings decided (RP-6b), budget open |
| 7 | Evaluation protocol | How is a result measured, compared and trusted? | S | not started |
| 8 | The three paradigms | The RL result itself | L | not started |

Status is one of *not started*, *in progress (since date)* or *done (date)*. A
stage is *done* only when its "Done when" condition holds.

After stage 8 the layer is finished; the grid-method comparison (top-level
`AGENTS.md`) runs on top of it.

---

## Stage 1: the decision problem (the MDP)

**Question.** Without any learning: what does an agent observe, what can it do,
what does it get for it, and is that the problem the thesis means? The market
plan has fixed the market side (its *Hands to RL* lines); this stage turns that
into the action, reward and observation of `MarketEnv`.

**Read.** [market_env.py](../../core/env/market_env.py): the module docstring is
the contract; then `decode` (action → order), `step` (reward), `_observe`.

| Part | Check | Decisions |
|---|---|---|
| **Action** | Every order a participant may place can be expressed, and nothing else: `encode` → `decode` round trip; the net-position baseline through the environment places the orders the market's own rule places | RP-1a. "No order" as a quantity threshold (now) or a third `side` category. RP-1b. Price range [FiT, utility]. RP-1c. Quantity as a share of the eq. 15 bound |
| **Reward** | One step by hand: bill = profit − p_utility · deferred demand, for a buyer, a seller and an agent that does not trade (Studio Step page) | RP-1d. The bill as the reward (individual, monetary); its scale |
| **Observation** | For each decision the agent must take, the information it needs is in its observation (the paper's 42 signals and the peers' reputations, [Observation](../rl/observation.md)) | RP-1e. Forecasts in the observation, or the true values (now: true values, E-05); the KPIs' window (now: the day so far, E-10) |
| **Episode** | 24 steps, day = episode, termination not truncation; γ over 24 steps | RP-1f. γ (0.99 is almost undiscounted over 24 steps; 1.0 is defensible) |

**Done when** each row's check is written down with its result, and RP-1a to
RP-1f are decided. The headroom (how much there is to learn) comes from the
market plan, MP-6b.

**References.** Kanervisto et al., *Action Space Shaping in Deep RL* (CoG 2020):
how the action encoding changes learnability. Masson et al., *RL with
Parameterized Actions* (AAAI 2016) and Hausknecht & Stone, *Deep RL in
Parameterized Action Space* (ICLR 2016): the discrete + continuous action family
the paper's action belongs to.

---

## Stage 2: the learner on known answers (probes)

**Question.** Does PPO with a composite (categorical + Gaussian) distribution learn
what it should, in each paradigm, on problems whose answer is known?

**Read.** [probes.py](../../core/rl/envs/probes.py),
[probe_check.py](../../core/rl/scripts/probe_check.py) (the procedure, used by
[probe_ppo.py](../../core/rl/scripts/probe_ppo.py) and
[probe_paradigms.ipynb](../../notebooks/rl/probe_paradigms.ipynb), here or on the
cluster), the results in [v2.md §7](../v2.md); Andy Jones, *Debugging RL, Without
the Agonizing Pain* (the probe method).

**What exists.** Probes 1-6 pass in every paradigm, apart from a few continuous
means just outside the 0.15 tolerance (V1 behaves identically). Probes 7-10 (built
23 Oct 2026), one market feature each, every one with an exact answer:

| Probe | What it isolates | Why the market needs it |
|---|---|---|
| 7 Gated action | A continuous gate decides whether a categorical choice counts; a closed gate pays a small safe reward | The no-order region: side, price and partner get gradient from steps where they had no effect, and "never order" is a local optimum |
| 8 Mutual choice | Pairs are paid only when both name each other on opposite sides; naming the DSO is a safe outside option (a stag hunt) | Stage 1 of the clearing in miniature: coordination of the partner choice, DTDE vs CTDE vs CTCE |
| 9 Conditional part | The best level depends on the side | The factorised policy samples price and quantity independently of the side: while the side is undecided they are one compromise for both |
| 10 Long episode | 24 steps, reward at the end, value γ^(23−t) | The market's horizon (probes 1-6 have 1-2 steps) |

Probes 7 and 8 are built with the market's local optima on purpose. A failure at
the fast budget measures how hard the market's version is; `escalate` (2×, 4×,
8× the budget) separates "slow" from "broken". Probe 9's answer is reachable by a
factorised policy once the side is decided; it tests that the level follows.

**Done when** the result of every probe in every paradigm, with the budget it
passed at, is in the decision log with a one-line reading.

**Decisions.** RP-2a. The tolerance for continuous means (0.15) and the budget rule
(pass at 1× or 2×). RP-2b. Whether the factorised policy is kept (V2: yes) given
probe 9.

**References.** Fan et al., *Hybrid Actor-Critic RL in Parameterized Action
Space* (IJCAI 2019, H-PPO): PPO with separate discrete and continuous action
heads. Neunert et al., *Continuous-Discrete RL for Hybrid Control in Robotics*
(CoRL 2019): a factorised discrete + continuous policy (off-policy, MPO), with
the independence assumption discussed. Huang & Ontañón, *A Closer Look at Invalid Action Masking in
Policy Gradient Algorithms* (FLAIRS 2022): what masking does to the gradient,
relevant to the gate in probe 7.

---

## Stage 3: PPO design choices

**Question.** Which of PPO's settings follow from the method and the paradigm, and
must be fixed before tuning? These are the points where adding agents changes
training (the discussion of 22 Oct 2026).

**Read.** [config.py](../../core/rl/config.py),
[rl_defaults.py](../../core/rl_defaults.py), [ctce.py](../../core/rl/ctce.py),
[ctde.py](../../core/rl/ctde.py); RLlib's `ppo_torch_learner.py` (the loss).

| # | Topic | Now | Options | Paradigm |
|---|---|---|---|---|
| RP-3a | Entropy term | 0.01 × sum over the action parts (4 per agent, 4N in CTCE) | coefficient / N in CTCE (MAPPO's mean over agents); 0 (BenchMARL); per-part weights | CTCE mainly |
| RP-3b | Group reward | sum of the agents' rewards | mean (same optimum, value scale as DTDE) | CTCE |
| RP-3c | Value scale | no value normalisation; advantages standardised per module | value normalisation (PopArt); rely on reward scaling | all, CTCE most |
| RP-3d | Optimiser | one Adam and one global gradient clip (0.5) over actor and critic | separate optimisers and clips (MAPPO, BenchMARL) | all |
| RP-3e | Parameter sharing | none: one actor and critic per agent | shared with an agent ID (MAPPO, BenchMARL default) | DTDE, CTDE |
| RP-3f | CTDE critic input | `[o_i, o_1 … o_N]` (276 numbers for 5 agents; the shared market signals and KPIs repeated) | pruned global state (MAPPO's feature pruning) | CTDE |
| RP-3g | Clip range ε | 0.2 per agent; one joint ratio in CTCE | keep, and state its N-dependence | all |

**Done when** each row has a decision and a reason in the decision log, the chosen changes
are made, and probes 1-10 are run again.

**Decide on paper first**, run only what paper cannot settle: 3b and 3g can be
argued; 3a, 3c, 3d are cheap to test on the probes; 3e is a modelling choice
(heterogeneous households argue against plain sharing).

**References.** Yu et al., *The Surprising Effectiveness of PPO in Cooperative
Multi-Agent Games* (NeurIPS 2022): MAPPO's loss averaged over agents, value
normalisation, the critic's input, ε ≤ 0.2, parameter sharing. Sun et al., *Trust
Region Bounds for Decentralized PPO Under Non-stationarity* (AAMAS 2023): the
joint trust region grows with N under per-agent clipping; joint vs independent
ratios. Kuba et al., *Trust Region Policy Optimisation in Multi-Agent RL* (ICLR
2022, HAPPO): joint ratio as a product of agents' ratios. van Hasselt et al.,
*Learning Values Across Many Orders of Magnitude* (NeurIPS 2016, PopArt).
Christianos et al., *Scaling Multi-Agent RL with Selective Parameter Sharing*
(ICML 2021) and Papoudakis et al., *Benchmarking Multi-Agent Deep RL Algorithms in
Cooperative Tasks* (NeurIPS 2021 Datasets): when sharing helps. Bettini et al.,
*BenchMARL* (JMLR 2024): a reference implementation's defaults.

---

## Stage 4: diagnostics

**Question.** What must every run report so that a curve that does not rise can
be explained instead of guessed at?

**What `metrics.csv` has now** per module: total, policy and value loss, value
explained variance, entropy (summed over parts). **Missing:**

| Diagnostic | Why |
|---|---|
| Entropy per action part (side, quantity, price, partner) | One summed number hides which part collapsed or stayed random |
| Clip fraction and approximate KL per module | Whether updates are too large (or nothing moves). The KL is logged since 25 Oct (`use_kl_loss=True`, `kl_coeff=0.0`, RP-4a); the clip fraction needs a learner subclass |
| Gradient norm before clipping | Whether the 0.5 clip is active on every step (3d) |
| Behaviour per evaluation: share of no-order steps, side vs net position, price chosen, partner distribution, mutual-preference rate | What the policy actually does in the market (the step infos already hold it: `side`, `partner`, `partner_mutual`) |

**Done when** these appear in every run's record and in the Studio's Results page
(or a notebook), checked on one short run.

**References.** Huang et al., *The 37 Implementation Details of PPO* (ICLR Blog
Track 2022): which quantities to log; Engstrom et al., *Implementation Matters in
Deep Policy Gradients* (ICLR 2020).

---

## Stage 5: first learning on the market

**Question.** Does PPO learn the market at all, and which action part stops it?

**Approach.** One paradigm as the control: **DTDE** (no grouping, no central
critic; V1's best). One seed, a budget long enough for the curve to level off.
Compare with zero, the net-position rule and the market plan's headroom (MP-6b).

**If it does not beat the net-position rule**, the action ladder: learn one more
part per rung, the others fixed by the rule.

| Rung | Learned | Fixed |
|---|---|---|
| A | quantity, price | side from the sign of the net position, partner = none |
| B | + side | partner = none |
| C | + partner | — (the full V2 action) |

The rung at which the result drops names the obstacle; it is also a thesis result
in itself (what each part of [P1] eq. 2 costs to learn).

**Done when** DTDE's held-out result against the baselines and the ladder (if
needed) are in the decision log, with stage 4's diagnostics explaining the curve.

**Decisions.** RP-5a. Whether the full action stays the thesis's action, or a rung
below it with a stated reason. RP-5b. Which paradigm-independent problems (stage 3)
must be revisited.

**References.** Andrychowicz et al., *What Matters for On-Policy Deep Actor-Critic
Methods? A Large-Scale Study* (ICLR 2021): which choices matter most for PPO
(normalisation, initial action std, network size).

---

## Stage 6: budget and hyperparameters

**Question.** How many environment steps, and which settings, for every later run?

**Approach.** On DTDE, after stage 5: a budget curve (when does the held-out
result stop improving), then a small sweep of the settings Andrychowicz et al.
rank first: learning rate, batch size and epochs, entropy coefficient, initial
log-std. A few values each, two seeds. The same settings then go to every
paradigm (L-04 spirit: like for like).

**Done when** the budget (L-14) and the settings are fixed in an experiment file
and in the decision log, with the sweep that justifies them.

**Decisions.** RP-6a. Budget in environment steps (L-14). RP-6b. The settings for all
paradigms, or per paradigm with a reason.

---

## Stage 7: evaluation protocol

**Question.** How is a result measured, and when is a difference real?

| Topic | Decision |
|---|---|
| Score | RP-7a. Team score = sum of the agents' held-out bills (money, not the scaled reward) for every paradigm (L-03); per-agent bills next to it |
| Seeds | RP-7b. Number of seeds per combination (≥ 5) and the statistic: mean with a confidence interval, or IQM with bootstrap intervals |
| Days | RP-7c. Training and held-out days (now June / 1-14 July 2016); whether one season is enough |
| Baselines | RP-7d. Zero, net-position (best margin, MP-6b), random |
| Market KPIs | RP-7e. Which of the paper's KPIs are reported next to the bill |

**Done when** 7a-7e are decided (L-03, L-17) and the Results page shows them.

**References.** Henderson et al., *Deep RL That Matters* (AAAI 2018); Colas et
al., *How Many Random Seeds?* (2018); Agarwal et al., *Deep RL at the Edge of the
Statistical Precipice* (NeurIPS 2021, `rliable`); Gorsane et al., *Towards a
Standardised Performance Evaluation Protocol for Cooperative MARL* (NeurIPS 2022).

---

## Stage 8: the three paradigms

**Question.** With everything above fixed: how do CTCE, CTDE and DTDE compare on
the market?

**Approach.** The stage 6 settings and budget, the stage 7 protocol, all three
paradigms, all seeds. Read with L-02 in mind: CTCE is a centralised-information
baseline trained by the same approximate learner, not an upper bound.

**Done when** the comparison is in the decision log with its protocol, and the behaviour
diagnostics say *why* the paradigms differ (coordination through the partner
choice, credit assignment in CTCE).

**References.** de Witt et al., *Is Independent Learning All You Need in the
StarCraft Multi-Agent Challenge?* (2020, IPPO); Yu et al. (2022); Lowe et al.,
*Multi-Agent Actor-Critic for Mixed Cooperative-Competitive Environments* (NeurIPS
2017): the CTDE idea [P2] eq. 18 follows.

---

## Parking lot

Questions raised while working on a stage that belong elsewhere. Add, do not act.

| Raised in | Question | Belongs to |
|---|---|---|
| 22 Oct | SAC with the mixed action | After stage 8, if time allows |
| 22 Oct | Partner choice conditional on side (autoregressive policy) | Only if probe 9 and stage 5 show it is needed |
| 24 Oct | A shared central critic with separate policies, still estimating each agent's own value (agent ID or $[o_i, s]$ as input; value normalisation): does learning from every agent's examples help, or do the households' different returns interfere? Same operations per step as separate critics; the possible gain is data, not computation | After stage 8; compare with the per-agent critics (RP-3e) |
| 24 Oct | Group-wise policy sharing: one policy per kind of household (PV + battery, battery only, consumer), as in selective parameter sharing (Christianos et al. 2021) | After stage 8; one module per group in `config.py` |
