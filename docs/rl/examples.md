# Worked examples: one agent's action through the cycle

> The training cycle with numbers, for the market's mixed action: what each
> paradigm's modules receive, how the network's output becomes four
> distributions, how a sampled action becomes an order, how the ratio and the
> clip work on a composite action, and how a trained policy is evaluated. The
> step labels (A2, C3, ...) are those of [One training iteration](cycle.md);
> [The training cycle](training.md) lists what we change in RLlib and why.

!!! ours "How to read the colours"
    <span class="ours">Purple</span> is **ours**: code this implementation adds to
    RLlib, a setting it chooses differently from RLlib's default, or the market
    environment. The normal colour is RLlib's PPO, unchanged.

**The numbers.** Sizes and parameter counts are from the modules
`core/rl/config.py` builds. The log-probabilities, entropies, ratios and KLs were
computed with RLlib's own distributions (`TorchCategorical`, `TorchDiagGaussian`);
the rest is arithmetic on them. The network outputs, tariffs and limits are made
up for the example.

| File | What it defines | Section here |
|---|---|---|
| [state.py](../../core/rl/state.py) | <span class="ours">the global state: all observations joined in agent order</span> | 1 |
| [ctce.py](../../core/rl/ctce.py), [ctde.py](../../core/rl/ctde.py) | <span class="ours">the CTCE and CTDE wrappers, CTDE's own-observation actor</span> | 1, 4, 6 |
| [modules.py](../../core/rl/modules.py) | <span class="ours">the policy head: tanh mean, one learned log σ per part</span> | 2, 5 |
| [market_env.py](../../core/env/market_env.py) | <span class="ours">the action space, decoding an action into an order, the reward</span> | 1, 4, 6 |
| [learner.py](../../core/rl/learner.py) | <span class="ours">RLlib's PPO learner, also logging the clip fraction</span> | 5 |
| [policy.py](../../core/rl/policy.py), [train.py](../../core/rl/train.py) | <span class="ours">evaluation, baselines, the budget and the NaN stop</span> | 7, 8 |

## The example

Three market participants, listed by the environment in the order
`agent_2, agent_10, agent_1` (alphabetically `agent_1, agent_10, agent_2`: the case
that broke the original,
[L-05](../validation/rl.md#l-05-grouped-spaces-are-in-name-order-grouped-data-in-environment-order)).
Each observes $d_o = 42 + (N - 1) = 44$ numbers: the paper's 42 signals and its two
peers' reputations ([Observation](observation.md)). Each acts with the `Dict`
<span class="ours">([`_action_space`](../../core/env/market_env.py#L268-L279))</span>:

| Part | Space | Meaning |
|---|---|---|
| `side` | `Discrete(2)` | 0 sell, 1 buy |
| `quantity` | `Box([-1, 1])` | share of what the agent may trade this step |
| `price` | `Box([-1, 1])` | from the feed-in tariff ($-1$) to the utility price ($+1$) |
| `partner` | `Discrete(N + 1) = Discrete(4)` | an index into the agent's candidates |

The candidates are the other participants in scenario order, then the DSO, then
"no preference" ([`partners`](../../core/env/market_env.py#L281-L286)):

| Agent | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| `agent_2` | `agent_10` | `agent_1` | DSO | none |
| `agent_10` | `agent_2` | `agent_1` | DSO | none |
| `agent_1` | `agent_2` | `agent_10` | DSO | none |

The example follows `agent_10`.

## 1. What each module receives (A1)

The global state is the three observations side by side, **in the environment's
order** (<span class="ours">[`join`](../../core/rl/state.py#L26-L30)</span>):
$s = (o_2, o_{10}, o_1) \in \mathbb{R}^{132}$, where $o_2$ is `agent_2`'s
observation, and so on.

| | CTCE | CTDE | DTDE |
|---|---|---|---|
| Modules | one, `"group"` | three, one per agent | three, one per agent |
| `agent_10`'s module input | – (the group gets $s$, 132 numbers) | <span class="ours">$x_{10} = (o_{10}, s)$, 176 numbers</span> | $o_{10}$, 44 numbers |
| Actor reads | $s$ (132) | <span class="ours">the first 44 entries, $o_{10}$</span> | $o_{10}$ (44) |
| Critic reads | $s$ (132) | all 176 | $o_{10}$ (44) |
| Action space | <span class="ours">`Tuple` of the three agents' `Dict`s, in environment order</span> | its own `Dict` | its own `Dict` |
| Wrapper | <span class="ours">[`CTCEEnv`](../../core/rl/ctce.py#L46-L110)</span> | <span class="ours">[`CTDEEnv`](../../core/rl/ctde.py#L55-L103), [`CTDEPPOModule`](../../core/rl/ctde.py#L143-L149)</span> | none |

**Sizes** (2 × 256 tanh encoders, <span class="ours">actor and critic
separate</span>, linear heads):

| | Policy head outputs | Learned log σ | Actor parameters | Critic parameters |
|---|---|---|---|---|
| DTDE, per agent | 10 | <span class="ours">2</span> | 79 884 | 77 569 |
| CTDE, per agent | 10 | <span class="ours">2</span> | 79 884 | 111 361 |
| CTCE | 30 | <span class="ours">6</span> | 107 556 | 100 097 |

CTDE's actor is DTDE's actor; only the critic's first layer is wider, for the
global state. With 13 participants, as in `market_s2`, $d_o = 54$ and the CTCE
actor's input is $13 \times 54 = 702$ numbers, its head 260 outputs.

## 2. From the network's output to four distributions (A2)

The policy head outputs 10 numbers for `agent_10`, in RLlib's order for the `Dict`
(keys sorted: partner, price, quantity, side;
[`action_parts`](../../core/rl/modules.py#L56-L85)). Say:

| Position | 1-4 | 5 | 6 | 7 | 8 | 9-10 |
|---|---|---|---|---|---|---|
| Meaning | partner logits $z_\beta$ | price mean | price $\ell$ | quantity mean | quantity $\ell$ | side logits $z_\alpha$ |
| Head output | 0.4, −0.2, 0.9, 0.1 | 0.3 | 1.7 | 0.8 | −2.1 | −0.3, 0.5 |
| RLlib's head would use | the same | $m_p = 0.3$ | $\ell_p = 1.7$, $\sigma = 5.47$ | $m_q = 0.8$ | $\ell_q = -2.1$, $\sigma = 0.12$ | the same |
| <span class="ours">Our head uses</span> | the same | <span class="ours">$\tanh 0.3 = 0.291$</span> | <span class="ours">$\bar\ell_p = -0.7$, $\sigma = 0.497$</span> | <span class="ours">$\tanh 0.8 = 0.664$</span> | <span class="ours">$\bar\ell_q = -0.4$, $\sigma = 0.670$</span> | the same |

With <span class="ours">[`BoundedHead`](../../core/rl/modules.py#L121-L173)</span>
the outputs at positions 6 and 8 are replaced by the module's two learned numbers
$\bar\ell_p, \bar\ell_q$, the same whatever the observation; the means go through
tanh. With RLlib's head both would be whatever the network outputs for this
observation: here a price spread far wider than the whole action range, and a
quantity spread already small enough that the mean barely gets to explore.

The categorical probabilities (softmax of the logits):

| | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| partner | 0.254 (`agent_2`) | 0.139 (`agent_1`) | **0.419** (DSO) | 0.188 (none) |
| side | 0.310 (sell) | **0.690** (buy) | | |

## 3. Sampling and the log-probability (A3)

Each part is drawn on its own. Say the draws are partner 2 (DSO) and side 1 (buy),
and the Gaussian noise $\varepsilon_p = 0.5$, $\varepsilon_q = -1.2$:

$$
u_p = 0.291 + 0.497 \times 0.5 = 0.540,
\qquad
u_q = 0.664 + 0.670 \times (-1.2) = -0.140 .
$$

| Part | Sampled | $\log\mu$ | Entropy |
|---|---|---|---|
| partner | 2 | $\log 0.419 = -0.871$ | 1.301 |
| price | 0.540 | $-\frac{(0.540 - 0.291)^2}{2 \cdot 0.497^2} + 0.7 - 0.919 = -0.344$ | $-0.7 + 1.419 = 0.719$ |
| quantity | −0.140 | $-\frac{(-0.140 - 0.664)^2}{2 \cdot 0.670^2} + 0.4 - 0.919 = -1.239$ | $-0.4 + 1.419 = 1.019$ |
| side | 1 | $\log 0.690 = -0.371$ | 0.619 |
| **action** | | **−2.825** (sum) | **3.658** (sum) |

The batch stores the action (2, 0.540, −0.140, 1), $\log\mu = -2.825$ and the
distribution inputs after our head. The partner was drawn without regard to the
side: the policy could just as well have named `agent_1` while selling.

In CTCE the group's module does this for all three agents at once (30 outputs, 12
parts) and stores one log-probability, the sum over the 12 parts.

## 4. Into the market (A4-A5)

**A4.** Both continuous parts are inside $[-1, 1]$, so RLlib's rescale-and-clip
leaves them as they are. A $u_q = -1.3$ would reach the market as $-1$ while the
batch keeps $-1.3$.

**CTCE first** splits the group's `Tuple` by position
(<span class="ours">[`ungroup`](../../core/rl/ctce.py#L36-L43)</span>):

```python
{
    "agent_2": {...},
    "agent_10": {"partner": 2, "price": [0.540], "quantity": [-0.140], "side": 1},
    "agent_1": {...},
}
```

**A5, decoding** (<span class="ours">[`decode`](../../core/env/market_env.py#L412-L445)</span>).
Say `agent_10` may buy at most 2.5 kWh this step, and the step's tariffs are a
feed-in tariff of 0.05 and a utility price of 0.25 €/kWh:

| Part | Rule | `agent_10` |
|---|---|---|
| side | 0 sell, 1 buy | buy |
| quantity | <span class="ours">share $s = (q + 1)/2 = 0.430$; no order below 0.05; above it $(s - 0.05)/0.95 = 0.400$ of the limit</span> | $0.400 \times 2.5 = 1.00$ kWh |
| price | <span class="ours">$0.05 + \frac{0.540 + 1}{2}(0.25 - 0.05)$</span> | 0.204 €/kWh |
| partner | <span class="ours">candidate 2</span> | DSO |

So the order is "buy 1.00 kWh at up to 0.204 €/kWh, from the DSO": it skips the
preference matching and the double auction and goes to stage 3. With
$u_q < -0.9$ the share would be below 0.05 and `agent_10` would place no order at
all; then side, price and partner have no effect on its reward, but they still
get a gradient from that reward in C (the situation probe 7 tests).

## 5. The update: per-agent ratios and clips (C2, C3, C8)

The loss is RLlib's, once per module.

**Ratio (C2).** Some minibatches later `agent_10`'s network has moved a little:
partner logits (0.4, −0.2, **1.0**, 0.1), price output 0.35, quantity output 0.78,
side logits (−0.35, 0.55), $\bar\ell_p = -0.705$, $\bar\ell_q = -0.405$. Recomputed
for the stored action:

| | partner | price | quantity | side | whole action |
|---|---|---|---|---|---|
| $\log\pi_\theta$ | −0.814 | −0.299 | −1.221 | −0.341 | −2.674 |
| $\log\mu$ (stored) | −0.871 | −0.344 | −1.239 | −0.371 | −2.825 |
| $\rho$ | 1.059 | 1.046 | 1.018 | 1.030 | **1.162** |
| KL($\mu \,\|\, \pi_\theta$) | 0.0012 | 0.0042 | 0.0002 | 0.0011 | 0.0066 |

The whole action's ratio is the **product** of the parts' ratios,
$1.059 \times 1.046 \times 1.018 \times 1.030 = 1.162$, and the KL their sum. Each
part moved by 2-6 %; together they are at 16 %, inside $[0.8, 1.2]$.

**Clip (C3), per agent.** Say `agent_10`'s advantage is $\hat A = +0.8$:
$\min(1.162 \times 0.8,\ \text{clip}(1.162) \times 0.8) = 0.930$, the unclipped
branch, so `agent_10` still gets a gradient. One more small move on any part would
take the product past 1.2 and stop it for all four parts at once: the parts share
one clip.

**CTCE clips the product over all agents.** Say `agent_2`'s and `agent_1`'s parts
have moved to ratios 1.08 and 1.05. The group's one ratio is
$1.162 \times 1.08 \times 1.05 = 1.318$, with one advantage, say $+0.8$:

$$
S = \min(1.318 \times 0.8,\ 1.2 \times 0.8) = \min(1.054,\ 0.960) = 0.960 ,
$$

the clipped branch: **no gradient for any agent**, although each agent alone is
still inside the band. <span class="ours">The clip fraction</span>
([`PPOLearner`](../../core/rl/learner.py#L27-L52)) counts such rows; the more
agents, the sooner the product leaves the band.

**Where the gradient goes (C8).** On the first minibatch ($\rho = 1$, unclipped),
with $\hat A = +0.8$, the surrogate's push on each of `agent_10`'s inputs is
$\hat A \cdot \partial\log\pi / \partial(\text{input})$:

| Input | $\partial \log\pi / \partial(\text{input})$ | × $\hat A = 0.8$ | Reads as |
|---|---|---|---|
| partner logits | $1[c = 2] - P_c$: (−0.254, −0.139, 0.581, −0.188) | (−0.203, −0.111, 0.465, −0.150) | name the DSO more often |
| side logits | (−0.310, 0.310) | (−0.248, 0.248) | buy more often |
| price output | $\frac{u - m}{\sigma^2}$ <span class="ours">$\cdot (1 - m^2)$</span> $= 1.007 \times 0.915 = 0.921$ | 0.737 | raise the price mean |
| quantity output | $\frac{u - m}{\sigma^2}$ <span class="ours">$\cdot (1 - m^2)$</span> $= -1.791 \times 0.559 = -1.001$ | −0.801 | lower the quantity mean |
| <span class="ours">$\bar\ell_p$</span> | $\frac{(u - m)^2}{\sigma^2} - 1 = -0.75$ | −0.600 | narrow the price spread (the sample was close to the mean) |
| <span class="ours">$\bar\ell_q$</span> | $\frac{(u - m)^2}{\sigma^2} - 1 = 0.44$ | 0.352 | widen the quantity spread (the sample was far out) |

The loss is $-S$, so gradient descent moves each input in the direction of the
"× $\hat A$" column. On top, the entropy term adds $c_H = 0.01$ to every
$\bar\ell$'s push and pushes the logits towards uniform. The
<span class="ours">tanh factor</span> $1 - m^2$ shrinks the push on a mean as it
nears $\pm 1$ (0.559 already at $m_q = 0.664$). Because
<span class="ours">$\bar\ell_p$, $\bar\ell_q$</span> are one number each for all
states, their gradient is the average of this column over the 64 rows of the
minibatch, and Adam moves them by about $3 \cdot 10^{-4}$ per step.

In CTCE all twelve parts' pushes would carry the group's one advantage; in CTDE
and DTDE each agent's carry its own.

## 6. Whose reward each module learns from (A5, B4)

The market pays each agent its bill for the step,
<span class="ours">$(\text{profit} - p_\text{utility} \cdot \text{unmet demand}) / \text{reward scale}$</span>
([`step`](../../core/env/market_env.py#L376-L381)). Say:

$$
r_2 = 1.50, \qquad r_{10} = -0.50, \qquad r_1 = 0.25 .
$$

| | CTCE | CTDE | DTDE |
|---|---|---|---|
| Reward the learner sees | <span class="ours">one, $R = 1.25$ for the group</span> | each module its own: 1.50, −0.50, 0.25 | each module its own: 1.50, −0.50, 0.25 |
| Critic learns | the group's return, about $N$ times one agent's | each agent's own return, from the whole state | each agent's own return, from its own observation |
| Advantage | one for the group | one per agent | one per agent |

**CTCE.** The agents' own rewards travel along in the group's `infos` (for
evaluation), but the learner sees only 1.25. `agent_10`'s DSO purchase is
reinforced or discouraged by the same number as `agent_2`'s order, although here
`agent_10` lost money and `agent_2` earned it: the credit-assignment cost of
[L-02](../validation/rl.md#l-02-ctce-is-a-centralised-information-baseline-not-an-upper-bound).

**CTDE and DTDE.** `agent_10`'s loss of 0.50 lowers only `agent_10`'s advantage.
CTDE's critic sees the whole state, so it can learn, for example, that `agent_10`
pays more whenever the others have no surplus to sell, and not blame `agent_10`'s
own bid for that.

## 7. Evaluating a trained policy

<span class="ours">[`Policy`](../../core/rl/policy.py#L92-L173)</span> acts with the
trained modules outside RLlib, the same way RLlib does in training, but without
noise: each part takes its most likely value. It builds each module's input as the
paradigm's wrapper does ($o_i$, $x_i$ or $s$) and always runs in the original
multi-agent environment. For `agent_10` with the outputs of section 2:

| Part | Most likely value | In the market |
|---|---|---|
| partner | the largest probability, 0.419 | DSO |
| side | 0.690 | buy |
| price | the mean, 0.291 | $0.05 + 0.646 \times 0.20 = 0.179$ €/kWh |
| quantity | the mean, 0.664 | share 0.832 → $0.823 \times 2.5 = 2.06$ kWh |

The mean is taken after our head, so it is already inside $(-1, 1)$. Evaluation
and training can order quite different amounts: here 2.06 kWh against the sampled
1.00. During training the noise spreads the quantity around the mean; in
evaluation it is the mean every time.

**Baselines** ([`baselines`](../../core/rl/policy.py#L450-L466)): "random" draws
every part uniformly; "zero" places no orders (quantity share 0, below the
threshold); <span class="ours">"net position"</span> is the market's own bidding
rule: offer the surplus, or ask for the deficit, left after the battery, priced 30 %
of the way from the feed-in tariff (selling) or the utility price (buying) into the
spread, with no partner
([`net_position_policy`](../../core/env/market_env.py#L667-L706)).

**The team score** ([`Episode`](../../core/rl/policy.py#L227-L248)). Every
paradigm is scored in the original multi-agent environment, from the per-agent
rewards. Over a day, say the three agents' returns are 2.10, 0.90 and 0.55: team
score $= 3.55$, reported with the three returns. The same number for CTCE, CTDE and
DTDE, computed the same way, so the paradigms and the baselines are ranked on one
scale ([L-03](../validation/rl.md#l-03-returns-of-the-paradigms-are-compared-across-different-scales)).
Periodic evaluation uses seeds from 1 000 000 on, which training never reaches;
the runner's held-out evaluation plays test days training never sees.

## 8. The run: budget, NaN stop, evaluation

<span class="ours">[`train`](../../core/rl/train.py#L408-L558)</span> repeats
RLlib's iteration until the budget of environment steps is used up.

**Budget.** `market_s2`: 240 000 environment steps with 500 per iteration, 480
iterations (about 10 000 market days), in every paradigm. With `eval_points = 10`
the policy and the baselines are evaluated at 0 (untrained, with the baselines),
then every 24 000 steps up to 240 000.

**NaN stop** (<span class="ours">[`_nonfinite`](../../core/rl/train.py#L346-L363)</span>).
After each iteration the learner's results are searched for losses and entropies
that are NaN or infinite. For

```python
{"agent_10": {"policy_loss": nan, "vf_loss": 0.31, "entropy": inf,
              "num_env_steps_trained_throughput": nan}}
```

it finds `agent_10/policy_loss` and `agent_10/entropy` and stops the run with an
error, which `run.json` records. The throughput is skipped on purpose: RLlib
reports it as NaN in the first iteration. The original carried on with zeroed
gradients
([L-07](../validation/rl.md#l-07-kl_coeff--0-does-not-switch-off-the-kl-term-and-a-nan-loss-goes-unnoticed)).
