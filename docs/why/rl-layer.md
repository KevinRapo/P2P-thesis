# Why the RL layer is built this way

> The learning layer is RLlib's PPO with a few pieces added. This page explains
> why: what the intended method needs, what RLlib provides, and what had to be
> added in between. It is about design, not defects. Even if the original release
> had none (its defects are in the [issue register](../validation/register.md)),
> these points would still have to change.

## At a glance

| The method needs | RLlib provides | Added here |
|---|---|---|
| A mixed action: side and partner chosen, quantity and price continuous ([P1] eq. 2) | A composite distribution for a `Dict` action: a categorical per discrete part, a Gaussian per continuous part | The `Dict` action and its decoding in [`MarketEnv`](../../core/env/market_env.py#L514-L547); no RLlib code |
| Continuous parts that keep exploring and stay in bounds | A state-dependent, unclipped log σ and an unbounded mean | [`BoundedHead`](../../core/rl/modules.py#L121-L173): one learned log σ per part, mean through tanh |
| CTCE: one controller for every agent | Training one agent per policy | [`CTCEEnv`](../../core/rl/ctce.py#L45-L106): the group as one agent |
| CTDE: own-observation actors, central critics | Actor and critic reading the same input | [`CTDEEnv`](../../core/rl/ctde.py#L55-L103) and [`CTDEPPOModule`](../../core/rl/ctde.py#L143-L149) |
| DTDE: independent learners | Exactly that, one module per agent | Nothing |
| Runs comparable across paradigms and repeatable | `algo.train()`, one iteration per call | [`train`](../../core/rl/train.py#L408-L555): a budget in environment steps, a stop on NaN, evaluation against baselines; [`PPOLearner`](../../core/rl/learner.py#L27-L52) logs the clip fraction |

The loss, the distributions, GAE, the optimiser and the networks stay RLlib's.

## 1. The action: discrete choices as categorical distributions

[P1] defines the action as $a_i = \langle p_\text{bid}, q_\text{bid}, \alpha, \beta \rangle$:
a price, a quantity, the side $\alpha$ and the preferred partner $\beta$. Calling the
space continuous, the original gives each agent one continuous `Box` of four numbers.
The policy is a Gaussian over them, and the two choices are read off by thresholds:
buy if $\alpha > 0.5$, partner `int(β)`
([original action](../marlem/learning/index.md#11-action-p1-eq-2)).

Even without the defects this encoding has, it does not match what the agent
chooses:

- **The partners get an order they do not have.** `int(β)` lays the candidates on
  a line. To move from agent 2 to agent 4, the mean has to pass through agent 3,
  and neighbouring indices always get similar probabilities. Which peer is
  "next to" which is an artefact of the list order.
- **PPO sees the wrong probability.** The probability of choosing partner $k$ is
  the Gaussian's mass on $[k, k + 1)$. PPO's ratio uses the density of the sampled
  number instead, so two samples that make the same choice get different ratios
  and different gradients. Likewise, the entropy bonus rewards the spread of a
  number, not uncertainty between the choices.
- **The edges collect the rest.** Samples outside the range are clipped to the
  bounds, so the first and last choices also receive all the mass beyond them. In
  the release, "no preference" sits at the upper bound itself and is almost never
  chosen ([E-04](../validation/register.md#E-04)).
- **There is no "no order".** Every step places an order
  ([M-08](../validation/register.md#M-08)).

The usual treatment of such a hybrid action is a categorical distribution for each
discrete choice and a Gaussian for each continuous parameter, with the joint
log-probability as their sum. RLlib does this by itself for a gymnasium `Dict`
action, so V2's action is a `Dict`: `side` and `partner` as `Discrete`, `quantity`
and `price` as `Box`. What is added is only the decoding into an order
([Action](../full-cycle/environment/action.md#e1-decode)):
- the quantity as a share of the agent's feasible bound, so no order is infeasible;
- "no order" below a share of 0.05;
- the price mapped between the step's two tariffs.

The policy stays **factorised**: each part is sampled independently given the
observation, so the partner cannot depend on the sampled side. An autoregressive
head would remove that limit but is not added.

## 2. The continuous parts: one learned spread, a bounded mean

For a `Dict` action, RLlib's head outputs each continuous part's mean and log σ as
plain linear outputs of the state:
- the mean has no bound;
- the log σ is not clipped, because RLlib's clip only fits a single `Box` action.

On the probes this failed in a way specific to the mixed action. While the side
was still undecided, the state-dependent log σ collapsed. After that, the price and
quantity means could no longer move. The means also drifted beyond the action
bounds, where the clipped action makes the reward flat
([probe 9](../full-cycle/learning/probes.md#9-conditional-part): log σ fell to
−5.5 and the level stuck, 0 of 6 runs passing in CTDE and DTDE over 3 seeds).

[`BoundedHead`](../../core/rl/modules.py#L121-L173) changes two outputs and nothing
else:
- one learned log σ per continuous part, the same in every state, as in MAPPO,
  CleanRL and Stable-Baselines3;
- each mean passed through tanh, so it stays inside the bounds.

The categorical logits and the distributions are RLlib's. With this head, probe 9
passed in 6 of 6 runs (decision RP-3h).

## 3. The paradigms

RLlib's multi-agent training gives each agent its own module, observation, reward
and update. That is **DTDE** as it is. The other two paradigms need a different
view of the same environment.

**CTCE** is one controller for all households, the social planner. `CTCEEnv`
presents the environment as one agent, `"group"`:
- it observes every agent's observation joined;
- it acts with a `Tuple` of every agent's `Dict` action;
- it is rewarded with the sum of the rewards.

RLlib then trains it as an ordinary single agent. The `Tuple` keeps each agent's
mixed action whole and in agent order, so nothing categorical is flattened into a
vector, and each part keeps its own agent's bounds
([L-05](../validation/rl.md#l-05-grouped-spaces-are-in-name-order-grouped-data-in-environment-order)).

**CTDE** is MAPPO: each agent acts on its own observation, while its critic sees
everything during training. RLlib's PPO module feeds the actor and the critic the
same input, so two pieces are added:
- `CTDEEnv` appends the global state to each agent's observation;
- `CTDEPPOModule` lets the actor read only the agent's own part.

Each agent keeps its own reward, critic and PPO clip, so CTDE differs from DTDE in
one thing only: what the critic sees.

Two choices here depart from [P2] by design:
- [P2]'s CTDE critic is $Q_\phi(s, \mathbf{a})$, over the joint action. PPO learns
  a state value, so the critic is MAPPO's $V_i(s)$.
- [P2]'s CTDE sums the rewards, a team objective. Here each agent learns from its
  own bill, because the market's prosumers are self-interested. CTCE keeps the
  summed objective as the planner's benchmark.

## 4. The training loop

`algo.train()` runs one iteration and returns its metrics. Comparing paradigms over
seeds needs more around it, so [`train`](../../core/rl/train.py#L408-L555) adds:
- **a budget in environment steps**, the same for every paradigm, instead of
  iterations ([L-14](../validation/rl.md#l-14-the-budget-is-counted-in-iterations-the-paper-in-episodes));
- **a stop on a non-finite loss**, so a NaN cannot pass silently
  ([L-07](../validation/rl.md#l-07-kl_coeff--0-does-not-switch-off-the-kl-term-and-a-nan-loss-goes-unnoticed));
- **evaluation** against the never-trade and net-position baselines on held-out
  days, with each action part's most likely value
  ([`Policy`](../../core/rl/policy.py#L92-L170)), and a `run.json` that records the
  run.

[`PPOLearner`](../../core/rl/learner.py#L27-L52) is RLlib's learner unchanged, except
that it also logs the **clip fraction**. This matters most for CTCE, where one ratio
covers every agent's action, so the clip stops the gradient sooner
([L-02](../validation/rl.md#l-02-ctce-is-a-centralised-information-baseline-not-an-upper-bound)).

Three of RLlib's defaults are changed because they work against this setup, not to
tune it:
- the value-loss cap is raised from 10, because RLlib caps the *squared* error, so
  a value error above about 3.2 gives the critic no gradient;
- the actor and critic do not share layers, so the value loss does not train the
  actor;
- the KL is logged as a gauge of each update's size and is not part of the loss.

The full list, with the tuned settings, is in
[Learning layer §2](../full-cycle/learning/index.md#2-everything-we-change-in-rllibs-ppo).

## Not added

- **An autoregressive policy**, which would choose the partner given the side (see §1).
- **Parameter sharing** between agents, **value normalisation** (PopArt) and
  separate actor and critic optimisers: none is needed for a correct method.
- **Population-based training**: a run has fixed settings and one seed. Tuning and
  seeds are loops around runs.
