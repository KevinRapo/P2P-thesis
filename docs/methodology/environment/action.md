# The action

> What an agent can do in the market, and how the environment turns it into an
> order: the paper's four-part action as `MarketEnv` encodes it, then its decoding
> in step E1.

## The mixed action

[P1] eq. 2 defines the action as $a_i = \langle p_{\text{bid}}, q_{\text{bid}}, \alpha, \beta \rangle$.
Each agent has a `Dict` action with these four parts
([market_env.py](../../../core/env/market_env.py)):

| Part | Space | Paper | Encoding chosen here |
|---|---|---|---|
| `side` | `Discrete(2)` | α, order type, categorical | 0 sell, 1 buy |
| `quantity` | `Box([-1, 1])` | $q_{\text{bid}}$, continuous | share $s = (q + 1) / 2$ of the agent's eq. 15a-b bound for the chosen side; **no order** when $s < 0.05$; above it the share is rescaled to $(0, 1]$ |
| `price` | `Box([-1, 1])` | $p_{\text{bid}}$, continuous | $p = p_{\text{FiT}} + \frac{p + 1}{2}\,(p_{\text{utility}} - p_{\text{FiT}})$ |
| `partner` | `Discrete(N + 1)` | β, another agent, the DSO or none | index into the agent's candidates: the $N - 1$ other participants in scenario order, then the DSO, then "no preference" |

What is the paper's: the four parts and their kinds. What is an implementation
choice: the quantity as a share of the eq. 15 bound (every order is feasible, so
none is rejected, E-04, E-05), the no-order threshold (an explicit encoding
decision: the paper has no "no order" action), the price range between the two
tariffs, and the candidate order. The original code decoded all four parts from
one continuous `Box` (`int(β)`, `α > 0.5`); here no categorical part
is decoded from a continuous number.

The chosen partner goes into `OrderIntent.partner_id` unchanged, "no preference"
(None) included. The scenario's rule-based partner choice
(`market.partner_preference`, [`choose_partner`](../../../core/market/agent/der.py))
only fills in orders the market's own bidding rule makes; it never replaces an RL
agent's choice. Partner choices are not masked, and certainly not with the other
agents' simultaneous actions, which are not known when the agent acts.

The clearing ([clearing.py](../../../core/market/clearing.py)) has three stages:

1. **Stage 1, preferences:** a buyer and a seller that named each other trade
   first, at the mechanism's price, when bid ≥ ask.
2. **Stage 2, double auction:** every order still open, except those naming the
   DSO.
3. **Stage 3, DSO:** whatever is left, and the orders naming the DSO.

So a choice is *compatible* (mutual, opposite sides, prices cross: stage-1
trade), *incompatible* (mutual but bid < ask: no stage-1 trade), or *one-sided*
(the partner named someone else or nobody: the order goes to the auction).
[test_partner_choice.py](../../../tests/market/test_partner_choice.py) plays each.

## E1. Decode

[`decode`](../../../core/env/market_env.py#L594-L627), per agent. The
action's four parts ([P1] eq. 2, above) become an
intent: `side` picks sell or buy, `partner` one of the agent's candidates (a peer,
the DSO or none), and the continuous `quantity` and `price` $a_q, a_p \in [-1, 1]$
become

$$
q = \frac{s - 0.05}{0.95}\, q_\text{max}, \quad s = \frac{a_q + 1}{2}, \qquad p = p_\text{FiT} + \frac{a_p + 1}{2}\,(p_\text{utility} - p_\text{FiT})
$$

where $q_\text{max}$ is eq. 15a (sell) or 15b (buy), $s < 0.05$ places no
order, and $p_\text{FiT}$, $p_\text{utility}$ are the tariffs of the step being
played: with a time-of-use price they change by the hour (MP-0b), so the same
$a_p$ means a different price at different hours. In CTCE, `CTCEEnv` first splits
the group's action into the agents' actions
([`ungroup`](../../../core/rl/ctce.py#L35-L42)).
