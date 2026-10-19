# RL layer: what is wrong and how it was tested

> Every problem found so far in the **reinforcement-learning layer** of MARLEM: in
> the original code, in the papers [P1] and [P2], or in the method itself. For each
> one, what is wrong, where it comes from, how it was found and, where a test
> exists, what the test showed. Nothing is fixed yet: this document records the
> state of the original. How the market and the RL layer connect (actions,
> observations, reward, KPIs) is left to a separate document.

## Scope and sources

**RL layer** means everything that turns an environment into trained policies,
independent of what the environment is:

- the three training paradigms (CTCE, CTDE, DTDE) and their RL modules;
- the grouping that turns all agents into one for CTCE and CTDE;
- the algorithm settings (PPO, APPO, SAC) and the trainer around them
  (Ray Tune, population-based training, evaluation, checkpoints);
- standalone inference of a trained policy.

The market environment itself (`lem.py`), and what it gives the agents
(observations, actions, reward, KPIs), is **not** in scope. To keep the two apart,
the original RL code was copied out of the original repository unchanged and tested
on small environments with known answers instead of the market (see
[The test bench](#the-test-bench)). That copy, with its issue markers and the test
notebooks, is kept in `RL/` at commit [`bbef313`](https://github.com/KevinRapo/P2P-thesis/tree/bbef31315e4c762d94bfd6600e29d38d61684c85/RL)
of the `clean` branch; the fixed layer is `core/rl/` here, still independent of the
market.

**Sources.**

- **IDs** are those of the [issue register](register.md), the single list of
  every issue in the original; this page gives the detail for the RL layer
  (`L-xx`), in the register's order.
- **The RL folder** (`RL/` at commit `bbef313` of the `clean` branch) holds the
  copied RL code, test environments, test bench and notebooks. Links below to the
  copied code and its notebooks point into it on GitHub, pinned to that commit.
- **The original code** is the authors' MARLEM repository,
  [salazarna/marlem](https://github.com/salazarna/marlem/tree/15d6715a7b7ad31700d3758f2a2dd9df053773a7),
  at commit `15d6715` (March 2026). Every code link and snippet points there,
  pinned to that commit. The RL files were copied unchanged into
  [core/rl/](https://github.com/KevinRapo/P2P-thesis/tree/bbef31315e4c762d94bfd6600e29d38d61684c85/RL/core/rl) (commit `bf58193`), so the line numbers are the same in
  both.
- **[P1]** is the MARLEM paper (Salazar-Peña et al., Applied Energy 412, 2026,
  127546). It describes the paradigms in words (§3.7) and leaves MARL training to
  future work.
- **[P2]** is the companion preprint (*Harnessing implicit cooperation: a
  multi-agent reinforcement learning approach towards decentralized local energy
  markets*, SSRN 6685504, not peer reviewed). It gives the paradigms' formulas
  (§3.4, eq. 16-20), the algorithms' objectives (§3.3, eq. 11-15) and trains the
  3 × 3 matrix of paradigms and algorithms (§4-5).
- **RLlib** is Ray 2.51.1, the version in the `marlem` conda env. Statements about
  RLlib's behaviour were checked in its installed source.

**Origin** (as in the register):

| Origin | Meaning |
|---|---|
| Paper | The paper itself is wrong, contradictory or silent where the method needs an answer |
| Fidelity | The original code does not do what the paper says |
| Code | A programming defect that the paper has nothing to say about |

**Evidence:**

| Evidence | Meaning |
|---|---|
| **Tested** | A test on the RL branch reproduces it; the result is given under the issue |
| **Read** | Found by reading the code; not tested yet. The issue says how it would be tested |
| **Judgment** | A question about the method that no test can settle; it needs a decision |

**Status.** This register describes the original implementation in `RL/core/rl/` (on the `clean` branch).
The rebuilt layer (`core/rl/` in this branch) names the issues it fixes in its module
docstrings, and [v1.md](../v1.md) gives its design and its probe and market results.
Nothing on this page describes the rebuilt layer unless it says so.
The only changes to the copied code isolate it from the market (the trainer takes
the environment class as an argument); each is marked `DEVIATION:` in the code, and
none changes how training works.

**In the code.** In `RL/core/rl/` (on the `clean` branch) every issue below is marked above the
lines at fault in `core/rl/`: `FAULT <ID>:` for a defect, `DECIDE <ID>:` for a
*Judgment* issue, so the document and the code can be read side by side. The markers use the
IDs from before October 2026 ([Earlier identifiers](register.md#earlier-identifiers)). The comments are the only
change; the line numbers in the links below are those of the original. L-18 is not
marked: the original's test file is not copied to the RL branch.

## Summary

| Part of the RL layer | Issues | Tested | Read | Judgment |
|---|---|---|---|---|
| [1. Training paradigms](#1-training-paradigms) | 4 | 2 | 1 | 1 |
| [2. Grouping the agents](#2-grouping-the-agents) | 1 | 0 | 1 | 0 |
| [3. Policy networks and loss](#3-policy-networks-and-loss) | 4 | 2 | 2 | 0 |
| [4. Trainer and hyperparameters](#4-trainer-and-hyperparameters) | 4 | 0 | 3 | 1 |
| [5. Inference, evaluation and tests](#5-inference-evaluation-and-tests) | 4 | 0 | 3 | 1 |
| **Total** | **17** | **4** | **10** | **3** |

The most consequential ones:

- **CTDE never trains the policies that act (L-01).** The loss trains a central
  actor; the agents act with per-agent networks that stay at their random initial
  weights for any algorithm and any training length. Confirmed by test: the acting
  networks change by exactly 0.
- **CTCE and CTDE policies can diverge to NaN and keep "training" (L-06, L-07).**
  Their action spread has no upper limit, so where the reward does not depend on
  the action the entropy bonus drives it to overflow. The KL term then becomes
  infinite, `kl_coeff = 0` turns that into a NaN loss, and RLlib silently zeroes
  the NaN gradients and carries on. Confirmed by test.
- **SAC's actor in CTCE and CTDE never learns from the critic (L-09).** It samples
  its action without the reparameterisation gradient, so it is trained only to
  raise its entropy.
- **The paradigms are not compared like for like (L-02 to L-04).** DTDE uses
  RLlib's standard network, CTCE and CTDE a smaller custom one without its
  safeguards; CTCE is trained on the sum of all rewards and learns more slowly.
- **Inference does not act like training (L-15).** It skips RLlib's rescaling of
  actions to the action bounds and reads the market metrics from the wrong place.
- **Nothing in the original checks that anything learns (L-16, L-18).** The
  trainer's test runs 5 iterations and asserts nothing, so L-01 passes it.

## How to read an issue

Each issue below has the same parts:

- **Header**: ID, title, origin, evidence.
- **Original code**: the lines at fault, copied from the original repository
  (salazarna/marlem, commit `15d6715`). The caption links to them on GitHub with
  their line numbers. `# ...` stands for lines cut for length.
- **Why it is wrong**: what the lines do, which other code or RLlib behaviour makes
  it a problem, and how that differs from [P1] or [P2].
- **Test** (evidence *Tested*): the **hypothesis**, the **test** that would show
  it, the **result**, and **what it tells us**.
- **How to test it** (evidence *Read*): the test that would confirm or refute it.

## The test bench

Validating RL code is harder than validating the market: a market rule can be
checked by computing one step by hand, but a learning defect usually shows only as
"the agents learn badly", which could also be the reward, the hyperparameters or
too little training. The bench is built so that a failure has only one possible
cause.

**Isolation.** The RL code runs on small test environments instead of the market
([core/rl/envs/](../../core/rl/envs)). They have the same interface as the market
environment (one `Box` observation and action per agent, per-agent rewards,
episodes that end), so the code under test is exactly the original's.

**What is trusted.** RLlib's algorithms themselves (the PPO, APPO and SAC losses,
advantage estimation, the optimiser) are widely used and not re-validated. What is
tested is MARLEM's own code around them: the grouping, the custom CTCE and CTDE
modules, and the trainer's settings.

**Probe environments** ([probes.py](../../core/rl/envs/probes.py)), after Andy Jones,
[*Debugging RL, Without the Agonizing Pain*](https://andyljones.com/posts/rl-debugging.html).
Each probe has an exact correct answer and adds one piece of the learning problem
to the previous one, so the first probe a paradigm fails names the broken piece.
All have 3 agents, one-dimensional observations and actions in [-1, 1], and a
reward per agent. For CTCE and CTDE the correct value is the sum over the agents,
since their reward is the group's sum.

| Probe | Observation | Reward | Correct answer | Adds |
|---|---|---|---|---|
| 1 Constant | always 0 | +1, one step | value 1 | value learning, reward delivery, episode end |
| 2 Observation | ±1, random per agent | the agent's observation | value = observation | the observation reaches the value network |
| 3 Discount | 0, then 1 | +1 only at the end of 2 steps | V(0) = γ, V(1) = 1 (γ = 0.5) | time, discounting, episode boundaries |
| 4 Action | always 0 | $1 - (a_i - t_i)^2$, targets −0.6, 0, 0.6 | action = $t_i$ | the policy gradient, each agent's own reward |
| 5 Obs → action | ±1, random per agent | $1 - (a_i - o_i/2)^2$ | action = $o_i/2$ | the policy uses the agent's own observation |
| 6 Agent order | as 4, agent names `agent_2, agent_10, agent_1` | as 4 | as 4 | agents stay matched when names sort differently |

"Observation always 0" means each agent receives the number 0: the network still
gets an input, but it carries no information, so the problem becomes "learn one
constant". That removes input processing from the list of suspects.

**Measurements.**

- **The learned networks are read directly** ([probe.py](https://github.com/KevinRapo/P2P-thesis/blob/bbef31315e4c762d94bfd6600e29d38d61684c85/RL/core/rl/probe.py)):
  after training, the learner's value and action outputs are queried in the
  probe's states and compared with the correct answer (tolerance 0.15; values 0.15
  times the size of the answer). Return curves are not used to judge a probe; they
  mix in exploration noise.
- **Which networks training changes**: each group of parameters is copied before
  training and compared after. A network that does not move is not being trained.
- **Learner health**, as Jones recommends: entropy, KL between old and new policy,
  policy and value loss, and whether any loss is NaN or infinite
  ([local.py](https://github.com/KevinRapo/P2P-thesis/blob/bbef31315e4c762d94bfd6600e29d38d61684c85/RL/core/rl/local.py)).

**Controls.** DTDE uses RLlib's own network for each agent, so it is the control
group: a probe that DTDE passes is solvable with these settings and this budget,
and a paradigm that fails it fails because of MARLEM's code. Probes 1-3 passing in
a grouped paradigm clears the grouping (rewards, observations, episode ends) before
its policy is examined.

**Settings.** PPO with the original's settings except the learning rate (3e-4, the
usual PPO value; the original starts at 1e-5 and relies on population-based
training to raise it), 1000 environment steps per iteration, 10 iterations for
probes 1-3 and 20 for 4-6. Training runs in one process with the trainer's own
algorithm configuration (`build_local`), not through Ray Tune; the Tune path is not
tested yet.

**Results** ([probe_paradigms.ipynb](https://github.com/KevinRapo/P2P-thesis/blob/bbef31315e4c762d94bfd6600e29d38d61684c85/RL/notebooks/original/probe_paradigms.ipynb)):

| Probe | DTDE | CTCE | CTDE |
|---|---|---|---|
| 1 Constant | pass | pass (3.04 for 3) | pass (2.98 for 3) |
| 2 Observation | pass | pass, but the loss went NaN (L-07) | pass |
| 3 Discount | pass | pass | pass |
| 4 Action | pass | **fail**: −0.80, 0.01, 0.73 | **fail**: −0.01, 0.19, 0.11 |
| 5 Obs → action | pass | **fail**: largest error 0.18 | **fail**: largest error 0.67 |
| 6 Agent order | pass | pass | **fail**: largest error 0.50 |

A second notebook, [validate_rl.ipynb](https://github.com/KevinRapo/P2P-thesis/blob/bbef31315e4c762d94bfd6600e29d38d61684c85/RL/notebooks/original/validate_rl.ipynb), trains
the three paradigms on two slightly larger tasks with known best returns and gives
the same picture: DTDE learns, CTCE learns slowly, CTDE does not learn.

### What the tests confirm works

Not every check found a problem. These parts behave correctly in every paradigm:

| What | Shown by |
|---|---|
| Rewards reach the learner; the grouped reward is the **sum** over agents ([P2] eq. 17) | Probe 1: grouped value 3.04 and 2.98 for 3 agents |
| Each agent's observation reaches the value network, and the critic tells agents apart | Probe 2, including the mixed state (+1, −1, +1 → 1) |
| Episodes end where they should; discounting uses the configured γ | Probe 3 with γ = 0.5 |
| DTDE trains each agent's own policy on its own reward and observation | Probes 4-6 |
| CTCE keeps observations, actions and rewards matched to the right agent, also when agent names sort differently | Probes 4-6 (direction and order right), probe 6 |
| CTDE's acting networks each read only their own agent's observation (decentralised execution is wired correctly) | Probe 5: each agent's output depends only on its own observation |

## 1. Training paradigms

### L-01: CTDE never trains the policies that act

**Fidelity · Tested**

[`src/environment/ctde.py` L46-L57](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctde.py#L46-L57)

```python
# Centralized training: encoder and policy heads for centralized actor, and value head for centralized critic
self.pi_encoder = self._get_encoder_network(concat_obs_dim, embeddings_dim)
self.pi = self._get_head_network(embeddings_dim, concat_act_dim * 2)
self.vf_head = self._get_head_network(embeddings_dim, 1)

# Decentralized execution: each agent gets its own separate policy heads
self.pi_heads  = torch.nn.ModuleDict({
    agent_id: self._get_network(input_dim=tuple_obs_space[i].shape[0],
                                output_dim=tuple_act_space[i].shape[0] * 2,
                                embedding_dim=embeddings_dim)
    for i, agent_id in enumerate(self.agents_id)})
```

[`src/environment/ctde.py` L86-L89, L104](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctde.py#L86-L104)

```python
# _forward_inference: used to act, during training and after it
obs_tuple = batch[Columns.OBS]["grouped_agents"]
action_logits = [self.pi_heads[agent_id](obs_tuple[i]) for i, agent_id in enumerate(self.agents_id)]
return {Columns.ACTION_DIST_INPUTS: torch.cat(action_logits, dim=-1)}

# _forward_exploration: used to collect training data
return self._forward_inference(batch, **kwargs)
```

[`src/environment/ctde.py` L121-L128](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctde.py#L121-L128)

```python
# _forward_train: what the loss is computed from
concat_obs = torch.cat(batch[Columns.OBS]["grouped_agents"], dim=-1)
central_embeddings = self.pi_encoder(concat_obs)
central_action_logits = self.pi(central_embeddings)

fwd_out = {Columns.ACTION_DIST_INPUTS: central_action_logits,
           Columns.EMBEDDINGS: central_embeddings}
```

**Why it is wrong.** The module holds two actors. The agents act with `pi_heads`,
one network per agent on its own observation, in data collection, evaluation and
inference. The loss is computed from `pi`, a central actor on all observations.
Nothing connects the two: `pi_heads` appear nowhere else except the target-network
bookkeeping, so no gradient ever reaches them, and every CTDE run acts with
randomly initialised networks, however long it trains.

[P1] §3.7.1 and [P2] §3.4.2 describe CTDE correctly: a centralised **critic**
during training, and "each agent *i* retains an independent policy network
$\pi_{\theta_i}(a_i \mid o_i)$", updated by [P2] eq. 18,

$$\nabla_{\theta_i} J(\theta_i) = \mathbb{E}\left[\nabla_{\theta_i} \log \pi_{\theta_i}(a_i \mid o_i)\; Q_\phi(s, a_1, \dots, a_I)\right].$$

The gradient is taken with respect to $\theta_i$, the parameters of the network
that acts. The code instead takes it with respect to the central actor's. The
comments show the mix-up: "centralized training" was implemented as "train a
central actor", while in CTDE "centralized" refers only to what the critic may
see.

The PPO update of the central actor is itself distorted. PPO's ratio compares the
new and old probability of an action *under the same policy*; here the actions were
sampled by the heads, so the ratio compares two different networks, starts far
from 1 and is mostly clipped.

The defect is in `_forward_train`, which PPO, APPO and SAC all use, so all three
CTDE combinations are affected. Inference acts through the same heads.

**Test.**

- *Hypothesis.* If the acting networks are never trained, CTDE passes the value
  probes (the critic is trained) and fails every policy probe, its actions do not
  move toward the answer, and the `pi_heads` parameters do not change at all.
- *Test.* Probes 1-6, plus the change of each parameter group over training.
- *Result.* CTDE passes probes 1-3 and fails 4-6. In probe 4 it outputs −0.01,
  0.19 and 0.11 for targets −0.6, 0 and 0.6. Over two iterations the parameters
  change by: `pi_encoder` 0.150, `pi` 0.114, `vf_head` 0.168, **`pi_heads` 0.000**.
  On the toy task ([validate_rl.ipynb](https://github.com/KevinRapo/P2P-thesis/blob/bbef31315e4c762d94bfd6600e29d38d61684c85/RL/notebooks/original/validate_rl.ipynb)) CTDE ends
  at −26.3, worse than always acting 0 (−10.1).
- *What it tells us.* The behaviour (policy probes fail, value probes pass), the
  mechanism (zero change in exactly the acting networks) and the code (heads not on
  the loss's path) agree. The defect is confirmed and fully explained. Only PPO was
  run; APPO and SAC follow from the code, not from a test.

### L-02: CTCE is a centralised-information baseline, not an upper bound

**Paper · Tested**

[`src/environment/train.py` L676-L687](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L676-L687)

```python
def step(self, action_dict: MultiAgentDict) -> Tuple[...]:
    obs, rewards, terminateds, truncateds, infos = self.env.step(action_dict)
    grouped_obs = {k: tuple(v) for k, v in obs.items()}
    # The reward for the group is the sum of individual rewards
    grouped_reward = sum(rewards.values())
    return grouped_obs, grouped_reward, terminateds["__all__"], truncateds["__all__"], infos
```

**Why it is wrong.** [P1] §3.7.1 calls CTCE "a theoretical upper bound for system
performance" and [P2] §3.4.1 "the theoretical upper bound for coordination quality",
and [P2] reports DTDE as a percentage of it ("91.7 % relative to the theoretical
centralized benchmark"). CTCE sees everything, so it *can represent* the best joint
policy, but it is trained by the same approximate learner on a harder problem: one
network outputs every agent's action and learns from the **sum** of all rewards.
The learning signal for agent *i*'s action carries every other agent's reward
noise, the classic credit-assignment problem that [P1] itself names as CTDE's
motivation. With a finite budget, CTCE can end below the decentralised paradigms;
"upper bound" holds at best in the limit.

**Test.**

- *Hypothesis.* With individual rewards, CTCE learns the same policy as DTDE but
  more slowly, because its gradient for each agent is noisier; it is not broken.
- *Test.* Probes 4-6 and the toy tasks, with the same settings and budget as DTDE.
- *Result.* On probes 4 and 5 CTCE moves every action in the right direction and
  order, and its entropy falls steadily (4.06 → 0.07 over 3 dimensions), but after
  20 iterations it is still up to 0.20 off (DTDE: 0.06). It passes probe 6. On the
  toy task it reaches −17.3 where DTDE reaches −3.7; on the team-reward task it is
  close to DTDE (−2.1 against −1.8). Clipping actions to [−1, 1] explains at most
  0.04 of the error at CTCE's final spread (computed).
- *What it tells us.* Consistent with "slow, not broken", but not proven: a longer
  CTCE run on probes 4 and 5 should pass if the hypothesis is right. That run is
  prepared and has not been run yet. Either way, [P2]'s percentages "of the CTCE
  benchmark" depend on how long CTCE was trained, not only on the paradigms.

### L-03: returns of the paradigms are compared across different scales

**Paper · Judgment**

Same lines as L-02.

**Why it is wrong.** CTCE and CTDE optimise the sum of all agents' rewards
([P2] eq. 17); DTDE optimises each agent's own return (eq. 19). [P2] Table 9 ranks
the nine combinations by one "mean episode reward". RLlib's reported episode
return for a multi-agent run is also the sum over agents, so the numbers may well
be on the same scale, but the papers do not say which number Table 9 shows, and a
per-agent mean would be smaller by the number of agents. The comparison needs one
stated team score, computed from the raw rewards the same way for every paradigm.

**How to settle it.** Decide the team score (sum or mean over agents, from raw
environment rewards) and report it alongside per-agent returns for every paradigm.

### L-04: the paradigms train different networks

**Code · Read**

[`src/environment/train.py` L337-L341](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L337-L341)

```python
# DTDE: RLlib's default module for each agent, default model config
agents_rl_module = {agent_id: RLModuleSpec(module_class=self.algorithm.get_module_class(),
                                           observation_space=agents_policy[agent_id].observation_space,
                                           action_space=agents_policy[agent_id].action_space)
                    for agent_id in self.env.agents_id}
```

[`src/environment/ctce.py` L290-L306](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctce.py#L290-L306)

```python
# CTCE and CTDE: custom encoder, embeddings_dim = 128 (train.py L166)
return torch.nn.Sequential(torch.nn.Linear(input_dim, embedding_dim, bias=bias),
                           torch.nn.ReLU(),
                           torch.nn.Linear(embedding_dim, embedding_dim, bias=bias),
                           torch.nn.ReLU())
```

**Why it is wrong.** DTDE uses RLlib's default network: two hidden layers of 256,
tanh, and a limit on the action spread. CTCE and CTDE use a custom network: two
layers of 128, ReLU (CTDE's acting heads add a third), and no limit on the spread
(L-06). A difference in results between paradigms is therefore
partly a difference in network size, activation and safeguards. [P2] attributes
its 3 × 3 differences to the paradigms and algorithms alone.

**How to test it.** Give all paradigms the same network and safeguards (or record
the difference as part of the paradigm), then repeat the comparison.

## 2. Grouping the agents

### L-05: grouped spaces are in name order, grouped data in environment order

**Code · Read**

[`src/environment/train.py` L646-L648](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L646-L648),
[L702-L705](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L702-L705)

```python
# GroupedLEM.__init__: RLlib packs the agents' data in env.agents_id order
self.env = env.with_agent_groups(groups={"grouped_agents": env.agents_id},
                                 obs_space=_tuple_obs_space,
                                 act_space=_tuple_act_space)

# _dict_to_tuple_space: the spaces are put in sorted name order
sorted_keys = sorted(dict_space.keys())
tuple_of_spaces = tuple(dict_space[key] for key in sorted_keys)
```

**Why it is wrong.** The k-th entry of the grouped observation and action is
agent `agents_id[k]`, but the k-th grouped *space* belongs to the k-th name in
alphabetical order. They differ whenever the names do not sort in environment order,
e.g. `agent_1` … `agent_10` (alphabetically `agent_1, agent_10, agent_2, …`).

Where the spaces have the same shape, data still lands in the right place, but
RLlib uses the action **bounds**: by default (`normalize_actions=True`) it rescales
each policy output from [−1, 1] to its space's `[low, high]`. In the market, each
agent's quantity bound is its own capacity
([`action.py` L35-L44](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/action.py#L35-L44)).
With such names, in CTCE and CTDE an agent's bid would be scaled to another agent's
capacity.

**Test so far.** Probe 6 (agents named `agent_2, agent_10, agent_1`) passes for
DTDE and CTCE: observations, actions and rewards stay matched. But all probe agents
have identical bounds, so the probe cannot show the wrong scaling.

**How to test it.** Probe 6 with different action bounds per agent: the correct
action of each agent is known in its own units, so a scaling with another agent's
bounds shows as a wrong answer.

## 3. Policy networks and loss

### L-06: the CTCE and CTDE action spread has no limit

**Code · Tested**

[`src/environment/ctce.py` L45](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctce.py#L45),
[L309-L322](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctce.py#L309-L322),
[L365](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctce.py#L365)

```python
self.pi = self._get_head_network(embeddings_dim, concat_act_dim * 2)  # mean + log_std

# _get_head_network
return torch.nn.Linear(embedding_dim, output_dim, bias=bias)

# _get_distribution_class
child_dist_cls = TorchDiagGaussian
```

[`src/environment/ctde.py` L360-L364](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctde.py#L360-L364)
(the per-agent heads end the same way)

**Why it is wrong.** For each action the policy outputs a mean and a log standard
deviation $\log\sigma$, and the action is drawn from a Gaussian. Its entropy per
dimension is $1.42 + \log\sigma$, and PPO's loss rewards entropy (coefficient 0.01).
Where the reward does not depend on the action, the reward gradient averages to
zero and the entropy bonus is the only steady force on $\log\sigma$, so it grows
for as long as training runs. RLlib's own networks clip $\log\sigma$ to ±20 (its PPO
default, `log_std_clip_param = 20`). MARLEM's custom heads are a plain linear
layer feeding `TorchDiagGaussian`, which does not clip, so $\log\sigma$ can grow
until $\sigma^2$ overflows the float32 range. In the market, a step where an
agent's bid cannot change its reward (no counterparty, a full battery) creates
exactly this condition.

**Test.**

- *Hypothesis.* In probe 2 (reward independent of the action) DTDE's entropy stops
  where RLlib's clip sits, while CTCE's and CTDE's grows without limit until it
  overflows.
- *Test.* Probe 2, with the learner's entropy and KL logged every iteration.
- *Result.* DTDE's entropy ends at 21.42, exactly $1.42 + 20$, RLlib's clip. CTCE
  reaches 147.9 and CTDE 151.3 over 3 dimensions, about $\log\sigma \approx 48$ per
  dimension; $\sigma^2$ exceeds float32, and the KL between old and new policy
  becomes infinite. At the original learning rate (1e-5) CTCE did not diverge
  within 6 iterations; at 3e-4 it diverged within 4.
- *What it tells us.* The missing clip is confirmed, and RLlib's clip is the
  exact difference. The speed depends on the learning rate and the entropy
  coefficient, both of which the original's population-based training raises
  (L-10). In CTDE the network that diverged is the central actor, which never acts
  (L-01); once the heads are trained, they have the same unbounded output.

### L-07: `kl_coeff = 0` does not switch off the KL term, and a NaN loss goes unnoticed

**Code · Tested**

[`src/environment/train.py` L216-L226](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L216-L226)

```python
return (PPOConfig()
        .training(lr=1e-5,
                  # ...
                  num_epochs=30,
                  minibatch_size=128,
                  kl_coeff=0.0,
                  entropy_coeff=0.01,
                  clip_param=0.2,
                  grad_clip=0.5))
```

**Why it is wrong.** Setting `kl_coeff=0.0` looks like it removes PPO's KL penalty.
In RLlib it does not: `use_kl_loss` stays on by default, so the learner still
computes the KL between the old and new policy and adds $0 \cdot \text{KL}$ to the
loss. When the KL is infinite (L-06), $0 \cdot \infty$ is NaN in floating point,
and the whole loss is NaN. RLlib's default response (`torch_skip_nan_gradients =
False`) is to replace NaN gradients with zero, log a warning and step on, warning
itself that this "can corrupt the internal state of the optimizer". Training
continues, metrics keep arriving, and the policy has stopped learning. The value
network does not depend on the KL and keeps learning, so value metrics look
healthy.

**Test.**

- *Hypothesis.* In the iteration where the KL becomes infinite, the total loss is
  NaN while the policy loss is still finite (the NaN comes from $0 \cdot \infty$, not
  from the policy itself), and the value network keeps learning afterwards.
- *Test.* Probe 2 with CTCE, logging total loss, policy loss and KL each iteration.
- *Result.* At iteration 4 (learning rate 3e-4): KL = ∞, total loss NaN, policy
  loss 0.005. From the next iteration on the policy loss is NaN too. The value
  check of probe 2 still passes (error 0.001). RLlib's log fills with "Gradients …
  contain nan/inf values" warnings (about 200 MB of them in the notebook).
- *What it tells us.* The mechanism is confirmed: a divergence that should stop a
  run instead degrades it silently. Any run of the original should be checked for
  NaN losses before its results are read.

### L-08: SAC in CTCE and CTDE uses an unsquashed Gaussian

**Code · Read**

[`src/environment/ctce.py` L358-L373](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctce.py#L358-L373)

```python
def _get_distribution_class(self) -> TorchMultiDistribution:
    tuple_space = self.action_space["grouped_agents"]
    child_dist_cls = TorchDiagGaussian
    # ... one TorchDiagGaussian per agent, for every algorithm
```

**Why it is wrong.** RLlib's SAC uses a tanh-squashed Gaussian for bounded actions
(`TorchSquashedGaussian`), so that sampled actions stay in bounds and the
log-probabilities and entropy in SAC's loss ([P2] eq. 15) are those of the actions
actually taken. The custom modules give SAC the same plain Gaussian as PPO, for both
CTCE and CTDE, while SAC-DTDE uses RLlib's squashed one. So SAC differs between
paradigms in its action distribution, and in CTCE and CTDE the entropy target
($-\sum \dim A_i$, [`train.py` L240](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L240))
applies to an unbounded distribution whose samples are clipped afterwards. [P2]
attributes SAC's very different results across paradigms ("excellent in CTCE and
CTDE … failing in DTDE") to the paradigms.

**How to test it.** Probes 1-6 with SAC in each paradigm. SAC has no value
function, so its value probes check the Q-values instead.

### L-09: SAC's actor in CTCE and CTDE gets no gradient from the critic

**Code · Read**

[`src/environment/ctce.py` L132-L146](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctce.py#L132-L146)
(`ctde.py` [L143-L157](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctde.py#L143-L157) is the same)

```python
# SECOND PASS: Compute Q-values for actions sampled from current policy to train the actor
curr_action_dist = self.action_dist_cls.from_logits(action_logits)
curr_actions_resampled = curr_action_dist.sample()
# ...
fwd_out["q_curr"] = torch.min(self.qf(curr_qf_embeddings).squeeze(-1),
                              self.qf_twin(curr_qf_twin_embeddings).squeeze(-1))
fwd_out["logp_resampled"] = curr_action_dist.logp(curr_actions_resampled)
```

**Why it is wrong.** SAC trains its actor on
$L_\pi = \alpha \log\pi_\theta(\tilde a \mid s) - \min_j Q_j(s, \tilde a)$ ([P2] eq. 15).
The second term is how the actor learns from the critic: $\tilde a$ must be a
*reparameterised* sample, $\tilde a = m_\theta(s) + \sigma_\theta(s)\,\varepsilon$, so
that the gradient flows through $\partial Q / \partial \tilde a$ into $\theta$.
RLlib's own SAC module does this with `rsample()`
([`default_sac_torch_rl_module.py` L155](https://github.com/ray-project/ray/blob/ray-2.51.1/rllib/algorithms/sac/torch/default_sac_torch_rl_module.py#L155)).
The custom modules call `sample()`, which draws without a gradient (checked:
`sample()` returns a tensor with `requires_grad=False`, `rsample()` one with
`True`). The $Q$ term is then a constant for the actor, and $\partial L_\pi /
\partial\theta$ comes from $\alpha \log\pi_\theta$ alone: the actor is trained only
to raise its entropy, never toward higher Q-values. The critic still learns, so Q
metrics look healthy.

So SAC-DTDE (RLlib's module) is SAC, but SAC-CTCE and SAC-CTDE are not: their
policies drift toward maximum spread regardless of the reward. In CTDE this adds to
L-01 (the trained actor does not even act). [P2] reports SAC as "excellent in CTCE
and CTDE … failing in DTDE".

**How to test it.** Probe 4 with SAC-CTCE: the action means should stay where they
start while the entropy rises; with `rsample()` they should move to the targets.
Directly: one SAC loss on a batch, then check that the actor's parameters receive a
gradient from the $Q$ term (zero now).

## 4. Trainer and hyperparameters

### L-10: population-based training jumps the learning rate and reaches entropy 10

**Code · Read**

[`src/environment/train.py` L178-L189](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L178-L189)

```python
if self.algorithm == RLAlgorithm.PPO:
    hyperparam_mutations = {"lr": loguniform(0.0001, 0.01),
                            "entropy_coeff": loguniform(0.01, 10.0),
                            "lambda_": loguniform(0.8, 0.99),
```

**Why it is wrong.** Training starts at `lr=1e-5` (L216), but the mutation domain
starts at 1e-4, so the first resample jumps the learning rate by 10-1000×. The
entropy coefficient can reach 10, a thousand times its starting value; at that
size the entropy bonus outweighs the reward in the loss. Together with L-06, the
search space contains exactly the settings that make CTCE and CTDE diverge, and with
L-07 those trials keep running with a NaN loss. [P2] ran 10 trials per combination
with these mutations (§4.2).

**How to test it.** Probe 2 with CTCE and CTDE at entropy coefficients across the
domain (0.01, 0.1, 1, 10): the iteration at which the KL becomes infinite should
fall as the coefficient rises.

### L-11: training configuration defects

**Code · Read**

[`src/environment/train.py` L116](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L116),
[L285-L293](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L285-L293),
[L426-L458](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L426-L458)

```python
# _check_init
if not (isinstance(self.evaluation_duration, str) and self.evaluation_duration == "auto") or (isinstance(self.evaluation_duration, int) and self.evaluation_duration <= 0):
    raise ValueError(...)

# _setup_extra_config
.env_runners(num_env_runners=self.cpus, sample_timeout_s=None)
# ...
.evaluation(evaluation_interval=self.evaluation_interval,
            # ...
            evaluation_num_env_runners=self.cpus,
            evaluation_parallel_to_training=True,

# train
if not ray.is_initialized():
    ray.init()
tuner = Tuner(..., scheduler=PopulationBasedTraining(...), ...)
results = tuner.fit()
# ...
ray.shutdown()
```

**Why it is wrong.**

- **A positive evaluation length is rejected.** `not A or B` is read as
  `(not A) or B`, so any integer, positive or not, raises. Only `"auto"` works.
- **CPUs are counted twice.** `cpus` sampling workers and another `cpus`
  evaluation workers run in parallel, each loading PyTorch. The default
  `cpus = cpu_count() − 4` (L154) gives 16 worker processes on a 12-thread machine.
  On this machine the workers failed with "The paging file is too small" when
  memory was short.
- **Population-based training is always on**, also for a single trial, so a plain
  run with fixed hyperparameters is not possible.
- **`ray.shutdown()` is not in a `finally`**, so a failed run leaves Ray running.

**How to test it.** Each is checkable directly: build the trainer with
`evaluation_duration=5`; count the worker processes of a run; run a trial that
raises and check whether Ray is still up.

### L-13: APPO's `lambda_` has no effect

**Code · Read**

[`src/environment/train.py` L186-L189](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L186-L189),
[L229-L235](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L229-L235)

```python
elif self.algorithm == RLAlgorithm.APPO:
    hyperparam_mutations = {"lr": loguniform(0.0001, 0.01),
                            "entropy_coeff": loguniform(0.01, 10.0),
                            "lambda_": loguniform(0.8, 0.99)}
# ...
return (APPOConfig()
        .training(lr=1e-5,
                  vtrace=True,
                  lambda_=0.95,
```

**Why it is wrong.** APPO computes its targets with V-trace, and RLlib's V-trace
takes no λ
([`vtrace_torch_v2.py` L72-L81](https://github.com/ray-project/ray/blob/ray-2.51.1/rllib/algorithms/impala/torch/vtrace_torch_v2.py#L72-L81));
nothing in APPO's learner reads `lambda_`
([`appo_torch_learner.py` L141-L150](https://github.com/ray-project/ray/blob/ray-2.51.1/rllib/algorithms/appo/torch/appo_torch_learner.py#L141-L150)).
The setting is ignored, and one of the three hyperparameters population-based
training searches for APPO searches nothing: trials that differ only in `lambda_`
are identical, and a "best `lambda_`" read from the results is noise. [P2] does not
mention λ for APPO.

**How to test it.** Two APPO runs with the same seed and `lambda_` 0.8 and 0.99:
their losses should match step for step.

### L-14: the budget is counted in iterations, the paper in episodes

**Paper · Judgment**

[`src/environment/train.py` L440](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L440)

```python
stop={TRAINING_ITERATION: self.iters if _iters is None else abs(int(_iters)),
```

**Why it is wrong.** [P2] §4.2 trains "for a total of 10 000 episodes". The
trainer stops after a number of *training iterations*, each of which collects a
batch of environment steps (4000 by default for PPO, 166 market days of 24 steps).
10 000 iterations and 10 000 episodes differ by two orders of magnitude, and the
papers do not say which was meant. Budgets also matter for the paradigm comparison
(L-02): CTCE needs more data than DTDE to reach the same policy.

**How to settle it.** State the budget in environment steps, the same for every
paradigm and algorithm.

## 5. Inference, evaluation and tests

### L-15: standalone inference does not act like training

**Code · Read**

[`src/environment/inference.py` L159-L174](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/inference.py#L159-L174)

```python
# The model outputs mean + log_std for each action dimension
means = action_dist_params[..., :action_dim]
# ...
else:
    sampled_actions = means

# Clip actions to valid range
actions[agent_id] = np.clip(sampled_actions,
                            a_min=action_space.low,
                            a_max=action_space.high)
```

[`src/environment/inference.py` L229-L232](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/inference.py#L229-L232),
[`src/environment/lem.py` L486](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L486)

```python
# inference: market metrics read from the top level of info
if info and isinstance(info, dict):
    price_history.append(info.get("market_price", 0.0))

# lem.step: info is keyed by agent
infos = {agent_id: self.info for agent_id in self.agents_id}
```

**Why it is wrong.**

- **Actions are not rescaled.** In training, RLlib treats the policy's output as a
  value in [−1, 1] and rescales it to the action's bounds
  (`low + (a + 1)(high − low)/2`, `normalize_actions=True` by default). Inference
  takes the policy's mean as the action itself and only clips it. A trained output
  of 0.5 for the bid price means 75 % of the price range in training, but a price
  of 0.5 in inference. Inference evaluates a different policy from the one trained.
- **The market metrics are always 0.** The environment returns one info dict per
  agent, so `info.get("market_price")` never finds the key, and the mean price,
  volume and grid balance reported by inference are 0.
- **CTDE inference acts with the untrained heads** (L-01).

**How to test it.** Run a trained DTDE probe policy through `RLInference` and
through RLlib's own evaluation, and compare the actions sent to the environment.

### L-16: no baselines, no seeds, no record of a run

**Code · Read**

**Why it is wrong.** The trainer has no way to evaluate a random or untrained policy
on the same scenario, runs one seed per trial, and saves no manifest of versions
and settings. A result such as "SAC-CTDE reaches 3158" cannot be compared with
what an untrained policy reaches, which is exactly the comparison that would have
exposed L-01. The probe notebooks report each result against fixed baselines (best,
always 0, random) for this reason.

**How to test it.** Not a test: a capability to add (random and untrained
baselines on held-out seeds, several training seeds, a run manifest).

### L-17: [P2]'s evaluation protocol cannot show generalisation or variance

**Paper · Judgment**

[`src/environment/train.py` L285-L293](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L285-L293)

**Why it is wrong.** [P2] fixes one global seed ("environmental conditions are
identical across all experimental runs"), evaluates on the training scenario, and
ranks by the shaped reward the agents were trained on. That shows how well each
combination fits one scenario, not how it generalises, and with one seed there is no
variance to compare. The ranking of Table 9 cannot separate a real difference from
seed luck.

**How to settle it.** Decide the protocol: held-out days or seeds for evaluation,
several training seeds per combination, and a score that is not the training
reward alone.

### L-18: the trainer's test checks that it runs, not that it learns

**Code · Read**

[`tests/test_trainer.py` L35-L44](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/tests/test_trainer.py#L35-L44),
[L144-L145](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/tests/test_trainer.py#L144-L145)

```python
trainer = RLTrainer(env_config=env_config,
                    algorithm=...,
                    training=...,
                    iters=5,
                    # ...
results, training_metrics = trainer.train()   # then prints metrics

# run_tests
test_trainer(algo="ppo",  # ppo, appo, sac
             mode="dtde")  # ctce, ctde, dtde
```

**Why it is wrong.** The test trains 5 iterations and prints the metrics; it
asserts nothing about learning, and by default it runs only PPO-DTDE. A smoke test
like this cannot catch a learning defect: a CTDE run executes without errors, logs
moving losses (the central actor *is* being trained) and saves checkpoints. L-01
passes it. The register's L-18 covers the whole test suite; this is its RL part.

**What replaces it.** The probe notebooks are the first learning tests: each probe
has an exact answer, and the parameter-change check fails a frozen actor. They are
notebooks, not automated tests. In marlem-v1, `tests/rl/` checks the probe
environments and the CTDE structure; learning on the probes still runs from
`notebooks/rl/probe_paradigms.ipynb` (results in [v1.md §5](../v1.md#5-validation)).

## Problems in the papers' RL method

What the papers leave wrong or open, whatever the code does. Each needs a recorded
decision.

| Topic | The problem in [P1] / [P2] | Issues |
|---|---|---|
| CTCE as upper bound | Called a theoretical upper bound, but trained by the same approximate learner on the summed reward; it learns more slowly | L-02 |
| Comparing returns | One "mean episode reward" across paradigms whose objectives are a group sum (eq. 17) and per-agent returns (eq. 19); the score is not defined | L-03 |
| CTDE critic | Eq. 18 uses a joint-action critic $Q_\phi(s, \mathbf{a})$; PPO and APPO learn a state-value critic $V(s)$. "CTDE" names a family, not one method | L-01 |
| Budget | "10 000 episodes"; the code counts iterations | L-14 |
| Evaluation | One seed, evaluation on the training scenario, ranking by the training reward | L-17 |
| Network design | Not described; the paradigms use different networks (L-04) and the custom ones lack RLlib's safeguards (L-06, L-08) | L-04 |

## What this means for the published results

**[P1] is not affected.** Its results use zero-intelligence agents (random bids);
it states that "full MARL training is deferred to future work". The defects above
affect the framework [P1] presents, including its highlight of "the first true,
like-for-like comparison of … CTCE, DTDE and CTDE", not its numbers.

**[P2] trains the 3 × 3 matrix.** Its hyperparameters (Table 8: learning rate 1e-5,
entropy 0.01, clip 0.2, gradient clip 0.5, minibatch 128, buffer 1000) are the
original code's. If its runs used this code, which cannot be confirmed
independently:

- **Every CTDE result comes from untrained policies (L-01).** PPO-CTDE (mean
  3004.8), APPO-CTDE and SAC-CTDE (mean 3158.2) acted with the heads' initial
  weights. [P2] reads SAC-CTDE's low standard deviation (42.5) as "the centralized
  critic successfully guided the local actors"; a policy that never changes also
  varies little. That untrained policies score close to CTCE (3099-3144) also says
  the reward hardly separates trained from untrained behaviour, a question for the
  connection document.
- **CTCE and CTDE trials may have run with NaN losses (L-06, L-07, L-10).** With
  population-based training raising the entropy coefficient toward 10, trials of
  the grouped paradigms are exactly the ones whose spread can diverge, and the
  original would keep reporting them.
- **SAC-CTCE and SAC-CTDE policies were never steered by their critics (L-09).**
  Their actors only gained entropy, so [P2]'s SAC results in the grouped
  paradigms ("excellent in CTCE and CTDE") come from policies that did not learn
  from the reward.
- **APPO's λ search found nothing (L-13)**: `lambda_` has no effect in APPO.
- **The ranking mixes paradigm with network (L-04, L-08)** and with training
  length (L-02), on one seed (L-17).

So [P2]'s conclusions about CTDE ("a robust middle ground", "the optimal choice"
for SAC) are **not supported** by the original code, and its comparisons between
paradigms need the fixes above before they can be repeated.

## Not tested yet

Open checks of the **original** code. The rebuilt layer passes all five probes in
all nine combinations of algorithm and paradigm ([v1.md §5](../v1.md#5-validation)).

| What | Why it matters | Issues |
|---|---|---|
| CTCE trained longer on probes 4 and 5 | Decides "slow, not broken" | L-02 |
| APPO and SAC on the probes | L-01 and L-06 follow from the code for them; SAC's distribution differs (L-08) | L-01, L-08 |
| SAC-CTCE on probe 4; the actor's gradient from the Q term | Confirms that SAC's grouped actors never learn from the critic | L-09 |
| Two APPO runs differing only in `lambda_` | Confirms the setting is ignored | L-13 |
| Probe 6 with different action bounds per agent | The only way to show the wrong action scaling | L-05 |
| The Ray Tune path (`RLTrainer.train`) | Population-based training, evaluation workers and checkpoints have not run; the bench uses `build_local` | L-10, L-11 |
| `RLInference` | Its action scaling and metrics | L-15 |
| Longer episodes and truncation | The probes are 1-2 steps long; the market has 24 or 96 | — |

## Outside this document

How the market and the RL layer connect is not covered here; its issues are listed
in the [register, part B](register.md#b-environment-and-cooperation). marlem-v1's
choices for the environment (objective, reward, action, days; E-04, E-05, L-17) are
in [v1.md §3](../v1.md#3-the-market-as-an-environment).

- **Actions and observations:** E-04 to E-07
- **Reward:** E-01, E-13 to E-22
- **KPIs:** E-08 to E-12, D-03
- **Experiments and reproducibility:** E-02, E-03, D-01, D-02, D-05
- **Docs:** D-04
