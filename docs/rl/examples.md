# Worked examples: the parts we define

> **V2 note.** This page describes V1 (PPO, APPO and SAC; the market's action as
> two numbers in one `Box`). V2 trains PPO only, with the mixed `Dict` action
> (side, quantity, price, partner) and CTCE's `Tuple` group action; what differs
> is in [v2.md](../v2.md), the observation in [Observation](observation.md). The
> settings here are V1's: V2's `SETTINGS` train 5 epochs on one minibatch of the
> whole 4000-step batch (after the MAPPO paper). Code links follow branch
> `marlem-v2`, so a line anchor may point near, not at, the V1 code described.

> The training cycle with numbers, limited to what our own code decides: what each
> paradigm's modules receive, how CTDE's local actor and central critic are put
> together, the settings we choose, and how a trained policy is evaluated.
> Everything else (the networks' layers, sampling, GAE, the losses, Adam) is
> RLlib's and is described in [One training iteration](cycle.md); it appears here
> only where our code feeds it or reads from it. Step labels (A4, C2, ...) are those
> of that page.

**The code** is the implementation in `core/rl/` in this repository. The links
point to the local files. Numbers that depend on the code were computed with it or
with RLlib's own functions (`unsquash_action`); the rest is arithmetic on them.

| File | What it defines | Section here |
|---|---|---|
| [state.py](../../core/rl/state.py) | the global state: all observations joined in agent order | 1 |
| [ctce.py](../../core/rl/ctce.py) | `CTCEEnv`: all agents as one (CTCE) | 1, 2, 4 |
| [ctde.py](../../core/rl/ctde.py) | `CTDEEnv`: each agent's observation with the global state; `CTDEPPOModule`: the actor on the agent's own observation (CTDE) | 1, 3, 5 |
| [config.py](../../core/rl/config.py) | the settings of each of the nine combinations | 6 |
| [policy.py](../../core/rl/policy.py) | acting with a trained policy, baselines, the team score | 7 |
| [train.py](../../core/rl/train.py) | the budget, the NaN stop, when evaluation runs | 8 |

## The example

Three agents, listed by the environment in the order `agent_2, agent_10, agent_1`
(alphabetically `agent_1, agent_10, agent_2`, the case that broke the original,
[L-05](../validation/rl.md#l-05-grouped-spaces-are-in-name-order-grouped-data-in-environment-order)).
Each observes 2 numbers and sets 2 actions: a quantity (kWh, negative = sell) and
a price (€/kWh). The quantity bound is each agent's own capacity.

| Agent | Observation $o_i$ | Quantity bounds | Price bounds |
|---|---|---|---|
| `agent_2` | (0.4, 0.8) | [−5, 5] | [0.05, 0.35] |
| `agent_10` | (−0.2, 0.5) | [−20, 20] | [0.05, 0.35] |
| `agent_1` | (0.9, 0.1) | [−2, 2] | [0.05, 0.35] |

So $N = 3$, $d_o = 2$, $d_a = 2$.

## 1. What each module receives (A1)

All observations side by side, **in the environment's order** (`join`,
[state.py L26-L30](../../core/rl/state.py#L26-L30)), are the global state

$$s = (\underbrace{0.4,\ 0.8}_{\texttt{agent\_2}},\ \underbrace{-0.2,\ 0.5}_{\texttt{agent\_10}},\ \underbrace{0.9,\ 0.1}_{\texttt{agent\_1}}) \in \mathbb{R}^6.$$

| | CTCE | CTDE | DTDE |
|---|---|---|---|
| Modules | one, `"group"` | three, one per agent | three, one per agent |
| Input of `agent_10`'s module | – (the group gets $s$) | $x_{10} = (\underbrace{-0.2,\ 0.5}_{o_{10}},\ \underbrace{0.4,\ 0.8,\ -0.2,\ 0.5,\ 0.9,\ 0.1}_{s}) \in \mathbb{R}^8$ | $o_{10} = (-0.2, 0.5)$ |
| Wrapper | [`CTCEEnv`](../../core/rl/ctce.py#L46-L107) | [`CTDEEnv`](../../core/rl/ctde.py#L57-L104) (`central_obs`, [L138-L144](../../core/rl/ctde.py#L48-L54)) | none |

**CTCE.** `CTCEEnv` turns the three agents into one agent, `"group"`, with
observation $s$. The action space is joined the same way (`join_spaces`,
[L34-L40](../../core/rl/state.py#L17-L23)), each agent's bounds in its own
slice:

| Position | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Belongs to | `agent_2` q | `agent_2` p | `agent_10` q | `agent_10` p | `agent_1` q | `agent_1` p |
| low | −5 | 0.05 | −20 | 0.05 | −2 | 0.05 |
| high | 5 | 0.35 | 20 | 0.35 | 2 | 0.35 |

To RLlib the group is an ordinary agent with a 6-dimensional `Box` observation and
action, so RLlib's own module and algorithm train CTCE without any custom network.

**CTDE.** `CTDEEnv` keeps the three agents. Each agent's observation
becomes its own $o_i$ followed by $s$, 8 numbers; its action space and reward stay
its own. The own part comes first so that the actor can read it as a fixed slice
(section 3).

**DTDE.** Nothing is wrapped: each agent's module gets its own $o_i$ and its own
bounds.

## 2. From the policy's output to the market (A3-A5)

Shown for CTCE, where one policy outputs all six dimensions; in CTDE and DTDE each
agent's module does the same for its own two.

**What RLlib does (A3).** Say the policy outputs, for the 6 dimensions, means and
log-stds

$$m = (0.30,\ -0.10,\ -0.60,\ 0.20,\ 0.10,\ 0.50), \qquad \ell = (-0.50,\ -1.00,\ -0.70,\ -1.20,\ -0.40,\ -0.90),$$

so $\sigma = e^\ell = (0.607, 0.368, 0.497, 0.301, 0.670, 0.407)$, and draws the
noise $\varepsilon = (1.0, -0.5, 0.2, 1.5, -2.0, 0.3)$:

$$u = m + \sigma\varepsilon = (0.907,\ -0.284,\ -0.501,\ 0.652,\ -1.241,\ 0.622).$$

**What our bounds decide (A4).** RLlib rescales each dimension from $[-1, 1]$ to
the bounds and clips,
$a_k = \text{clip}(\text{low}_k + (u_k + 1)(\text{high}_k - \text{low}_k)/2)$:

| Dimension | $u_k$ | low, high | $a_k$ |
|---|---|---|---|
| `agent_2` q | 0.907 | −5, 5 | −5 + 1.907 × 5 = **4.53** |
| `agent_2` p | −0.284 | 0.05, 0.35 | 0.05 + 0.716 × 0.15 = **0.157** |
| `agent_10` q | −0.501 | −20, 20 | −20 + 0.499 × 20 = **−10.01** |
| `agent_10` p | 0.652 | 0.05, 0.35 | **0.298** |
| `agent_1` q | −1.241 | −2, 2 | −2 + (−0.241) × 2 = −2.48 → clipped to **−2** |
| `agent_1` p | 0.622 | 0.05, 0.35 | **0.293** |

The same $u = -0.501$ would be −2.5 kWh for `agent_2` and −1.0 kWh for `agent_1`:
the bounds must belong to the right agent. The original put the bounds in sorted
name order (`agent_1, agent_10, agent_2`) but the data in this order, so positions
1-2 carried `agent_1`'s bounds and positions 5-6 `agent_2`'s: `agent_2` would have
bid $-2 + 1.907 \times 2 = 1.81$ kWh instead of 4.53, and `agent_1` would have been
clipped at −5 instead of −2, beyond its own capacity (L-05). `agent_10` happens to
sit in the middle of both orders and would have been right. In CTDE and DTDE the
question does not arise: each module has its own agent's space.

`agent_1`'s quantity shows the clip: $u = -1.241$ is outside $[-1, 1]$, so the
market gets the bound −2, but the batch keeps $u = -1.241$ and the learner trains
on it.

**Splitting back (A5, CTCE).** `CTCEEnv.step` cuts the joint action into the
agents' parts (`ungroup`, [L36-L43](../../core/rl/ctce.py#L36-L43)) and passes
them to the environment:

```python
{"agent_2": [4.53, 0.157], "agent_10": [-10.01, 0.298], "agent_1": [-2.0, 0.293]}
```

## 3. CTDE: a local actor and a central critic per agent (A2, B3)

Each agent's module is RLlib's default module for its algorithm, built for the
agent's 8-number input $x_i$, with one change: the actor's encoder is replaced by
the encoder RLlib builds for the agent's own 2-number observation, applied to the
first 2 entries of $x_i$ (`OwnObsEncoder` and `own_encoder`,
[ctde.py L110-L137](../../core/rl/ctde.py#L110-L137)). The policy head,
the critic, the losses and the action distribution stay RLlib's
([`CTDEPPOModule`](../../core/rl/ctde.py#L140-L145)).

For `agent_10`, with $x_{10}$ of section 1:

| Part | Reads | Output |
|---|---|---|
| Actor encoder | entries 1-2 of $x_{10}$: $(-0.2, 0.5) = o_{10}$ | a 256-number latent $h_{10}$ |
| Actor head | $h_{10}$ | $[m_q, m_p, \ell_q, \ell_p]$, e.g. (−0.60, 0.20, −0.70, −1.20) |
| Critic encoder and head | all 8 entries: $o_{10}$ and $s$ | $V_{\phi_{10}}(o_{10}, s)$, `agent_10`'s own expected return |

The actor's output is already in the order RLlib's Gaussian expects (*first the
means, then the log-stds*), since the head is RLlib's own for one agent's 2
dimensions. Changing any entry of $s$ changes the critic's value but never the
action: the trained actor can act on $o_{10}$ alone.

**Sizes** (RLlib's default network, 2 × 256 tanh, actor and critic separate):

| | Actor parameters | Critic parameters |
|---|---|---|
| DTDE, per agent | 67 588 (input 2, output 4) | 66 817 (input 2) |
| CTDE, per agent | 67 588 (input 2, output 4) | 68 353 (input 8) |
| CTCE | 70 668 (input 6, output 12) | 67 841 (input 6) |

CTDE's actor is DTDE's actor; only the critic's first layer is wider, for the
global state.

## 4. Whose reward each module learns from (A5, B4)

With the market paying

$$r_{\texttt{agent\_2}} = 1.50, \qquad r_{\texttt{agent\_10}} = -0.50, \qquad r_{\texttt{agent\_1}} = 0.25:$$

| | CTCE | CTDE | DTDE |
|---|---|---|---|
| Reward the learner sees | one, $R = 1.25$ for the group ([`CTCEEnv`](../../core/rl/ctce.py#L100)) | each module its own: 1.50, −0.50, 0.25 | each module its own: 1.50, −0.50, 0.25 |
| Critic learns | the group's return, about $N = 3$ times one agent's | each agent's own return, from the whole state | each agent's own return, from its own observation |
| Advantage | one for the group | one per agent | one per agent |

**CTCE.** The agents' own rewards travel along in the group's `infos` (for
evaluation), but the learner sees only 1.25. $\hat A$ is computed from $R$, so
`agent_1`'s bid is reinforced or discouraged by the same number as `agent_2`'s,
although here `agent_10` lost money and `agent_2` earned it. Telling the agents'
contributions apart is left to the averaging over many steps (the
credit-assignment cost,
[L-02](../validation/rl.md#l-02-ctce-is-a-centralised-information-baseline-not-an-upper-bound)).

**CTDE and DTDE.** `agent_10`'s loss of 0.50 lowers only `agent_10`'s advantage.
CTDE's critic sees the whole state, so it can learn, for example, that `agent_10`
loses money whenever the others have a surplus, and not blame `agent_10`'s own bid
for that.

## 5. CTDE in the update: per-agent ratios and clips (C2, C3, C8)

The loss is RLlib's, once per agent's module. Here is what that means in numbers,
against a grouped policy that would clip the agents together.

**Log-probability.** For the stored $u$ of section 2, per dimension
$\log\pi = -\frac{(u - m)^2}{2\sigma^2} - \ell - \frac12\log 2\pi$:

| | `agent_2` | `agent_10` | `agent_1` |
|---|---|---|---|
| $\log\mu(u_i)$ when sampled | −0.963 | −1.083 | −2.583 |

**Ratio (C2).** Some minibatches later the actors have moved a little: `agent_2`'s
quantity mean 0.30 → 0.36, `agent_10`'s price mean 0.20 → 0.235, `agent_1`'s price
mean 0.50 → 0.53. Recomputed:

| | `agent_2` | `agent_10` | `agent_1` |
|---|---|---|---|
| $\log\pi_{\theta_i}(u_i)$ | −0.869 | −0.915 | −2.563 |
| $\rho_i = e^{\log\pi_{\theta_i} - \log\mu_i}$ | 1.099 | 1.182 | 1.020 |

**Clip (C3), per agent.** Each module clips its own ratio to $[0.8, 1.2]$ with its
own advantage. Say $\hat A_2 = +0.8$, $\hat A_{10} = -0.6$, $\hat A_1 = +0.3$:

| | `agent_2` | `agent_10` | `agent_1` |
|---|---|---|---|
| $\rho_i \hat A_i$ | 0.879 | −0.709 | 0.306 |
| $\text{clip}(\rho_i)\, \hat A_i$ | 0.879 | −0.709 | 0.306 |
| Gradient | yes | yes | yes |

All three ratios are inside the band, so every agent keeps learning.

**A grouped policy would not.** With one product policy, as in CTCE or a grouped
CTDE, RLlib clips the joint ratio $\rho = 1.099 \times 1.182 \times 1.020 = 1.324$
with one advantage. With $\hat A = +0.8$,

$$S = \min(1.324 \times 0.8,\ 1.2 \times 0.8) = \min(1.060,\ 0.960) = 0.960,$$

the clipped branch: **no gradient for any agent**, although each agent alone is
still inside $[0.8, 1.2]$. Three agents that each moved a little count as one
policy that moved too far, and the more agents, the sooner the product leaves the
band. This is why CTDE is per agent (MAPPO); CTCE keeps the joint clip, since it
*is* one policy.

**Where the gradient goes (C8).** Agent $i$'s actor receives only its own term. On
the first minibatch ($\rho_i = 1$, unclipped) the push on each mean is
$\hat A_i \cdot \partial\log\pi_i / \partial m_k = \hat A_i\,(u_k - m_k)/\sigma_k^2$:

| | `agent_2` q | `agent_2` p | `agent_10` q | `agent_10` p | `agent_1` q | `agent_1` p |
|---|---|---|---|---|---|---|
| $(u_k - m_k)/\sigma_k^2$ | 1.649 | −1.359 | 0.403 | 4.980 | −2.984 | 0.738 |
| × own $\hat A_i$ (0.8, −0.6, 0.3) | 1.319 | −1.087 | −0.242 | −2.988 | −0.895 | 0.221 |

Each mean is pulled toward the action that was sampled when the agent's own
outcome was better than its critic expected ($\hat A_i > 0$), and away from it when
worse: `agent_10`'s means move away from its sampled action, the others' toward
theirs. In CTCE the six numbers would all carry the group's one advantage.

In the original, these gradients went to a central actor and the acting heads got
none ([L-01](../validation/rl.md#l-01-ctde-never-trains-the-policies-that-act)).

## 6. The settings we choose

[`SETTINGS` and `NETWORK`](../../core/rl_defaults.py#L22-L50), and what each changes in
the cycle:

| Setting | Value | What it does in the cycle |
|---|---|---|
| `lr` | $10^{-5}$ | Adam moves each weight about $10^{-5}$ per step (C10) |
| `gamma`, `lambda_` | 0.99, 0.95 | discount and GAE horizon, ≈ 17 steps (B4) |
| `num_epochs`, `minibatch_size` | 30, 128 | with RLlib's 4000 steps per batch: 30 × ⌈4000/128⌉ ≈ 940 gradient steps per iteration |
| `clip_param` | 0.2 | the band $[0.8, 1.2]$ of section 5 |
| `entropy_coeff` | 0.01 | the constant push to widen $\sigma$ (C5) |
| `grad_clip` | 0.5 | gradient norm capped at 0.5 (C9) |
| `use_kl_loss` | False | the KL term is not computed at all (C6 disappears; fixes [L-07](../validation/rl.md#l-07-kl_coeff--0-does-not-switch-off-the-kl-term-and-a-nan-loss-goes-unnoticed)) |
| `vf_clip_param` | $10^6$ | the value loss is not capped (C4) |
| `vf_share_layers` | False | actor and critic have separate encoders: the value loss does not train the actor's layers (C8) |
| SAC `target_entropy` | `"auto"` | $-\dim A$ of each module: **−2** per agent in CTDE and DTDE, **−6** for the group in CTCE |

An experiment can override them; the market runs use `lr` $3 \cdot 10^{-4}$, PPO
batches of 2400 steps (100 days), minibatches of 240 and 10 epochs.

**Steps per iteration.** One PPO iteration samples 4000 environment steps. In CTCE
that is 4000 rows of the group; in CTDE and DTDE 4000 rows for *each* of the three
modules, 12 000 rows in total, but still 4000 environment steps. The budget counts
environment steps, so all paradigms get the same amount of experience.

## 7. Evaluating a trained policy

[`Policy`](../../core/rl/policy.py#L91-L159) acts with the trained modules outside
RLlib, the same way RLlib does in training, but without noise. It builds each
module's input as the paradigm's wrapper does (`_inputs`: $o_i$, $x_i$ or $s$) and
always runs in the original multi-agent environment.

**The action** (`act`, [L135-L146](../../core/rl/policy.py#L135-L146)). The most
likely action is the mean, then RLlib's own rescaling, with each agent's bounds in
CTDE and DTDE and the joint bounds then a split in CTCE. The result is the same:

| | `agent_2` | `agent_10` | `agent_1` |
|---|---|---|---|
| PPO, APPO: $a = \text{rescale}(m)$ | (1.50, 0.185) | (−12.0, 0.230) | (0.20, 0.275) |
| SAC: $a = \text{rescale}(\tanh m)$ | (1.46, 0.185) | (−10.74, 0.230) | (0.199, 0.269) |

For example `agent_10`'s quantity: $-20 + (-0.60 + 1) \times 20 = -12.0$. SAC's
actions are squashed by tanh, so its most likely action is $\tanh m$; RLlib's own
deterministic SAC action skips the tanh in Ray 2.51.1, so `_deterministic`
([L85-L88](../../core/rl/policy.py#L85-L88)) applies it. The original's inference
used the mean without rescaling, so `agent_10` would have bid −0.60 kWh
([L-15](../validation/rl.md#l-15-standalone-inference-does-not-act-like-training)).

**Baselines** ([L140-L174](../../core/rl/policy.py#L175-L209)). "Random" draws each
action uniformly within its bounds. "Zero" sends 0 in the environment's units,
clipped to the bounds: quantity 0, price $\max(0, 0.05) = 0.05$ for every agent. It
is *not* the network's 0, which would be the middle of the bounds (price 0.20). The
market environment adds its own baselines (never trade, and the market's bidding
rule), see [marlem-v1](../v1.md#3-the-market-as-an-environment).

**The team score** (`Episode`, [L175-L195](../../core/rl/policy.py#L216-L236)).
Every paradigm is scored in the original multi-agent environment, from the raw
per-agent rewards. Over a 3-step episode:

| Step | `agent_2` | `agent_10` | `agent_1` |
|---|---|---|---|
| 1 | 1.50 | −0.50 | 0.25 |
| 2 | 0.80 | 0.30 | −0.10 |
| 3 | −0.20 | 1.10 | 0.40 |
| **Return** | **2.10** | **0.90** | **0.55** |

Team score $= 2.10 + 0.90 + 0.55 = 3.55$, reported with the three returns. The
same number for CTCE, CTDE and DTDE, computed the same way, so the nine
combinations and the baselines can be ranked on one scale
([L-03](../validation/rl.md#l-03-returns-of-the-paradigms-are-compared-across-different-scales)).
Evaluation episodes use seeds from 1 000 000 on, which training never reaches
(`evaluation_seeds`, [L248-L252](../../core/rl/policy.py#L415-L419)); the runner's
held-out evaluation uses test days that training never sees.

`Policy.values` gives each module's critic estimate of a state: in CTCE the group's
value, comparable to the team score; in CTDE and DTDE each agent's own expected
return.

## 8. The run: budget, NaN stop, evaluation

[`train`](../../core/rl/train.py#L378-L509) repeats RLlib's iteration until the
budget of environment steps is used up.

**Budget.** `budget = 100_000` with PPO's 4000 steps per iteration: 25 iterations,
for every paradigm. With `eval_every = 20_000`, the policy and baselines are
evaluated at 0 (untrained, together with the baselines), 20 000, 40 000, 60 000,
80 000 and at the end, 100 000
([L298-L317](../../core/rl/train.py#L449-L468)).

**NaN stop** (`_nonfinite`, [L204-L219](../../core/rl/train.py#L321-L336)). After
each iteration the learner's results are searched for losses, entropies and the SAC
temperature that are NaN or infinite. For

```python
{"agent_10": {"policy_loss": nan, "vf_loss": 0.31, "entropy": inf,
              "num_env_steps_trained_throughput": nan}}
```

it finds `agent_10/policy_loss` and `agent_10/entropy` and stops the run with an
error, which `run.json` records. The throughput is skipped on purpose: RLlib
reports it as NaN in the first iteration. The original carried on with zeroed
gradients
([L-07](../validation/rl.md#l-07-kl_coeff--0-does-not-switch-off-the-kl-term-and-a-nan-loss-goes-unnoticed)).
