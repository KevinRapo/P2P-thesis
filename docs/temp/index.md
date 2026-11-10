# Work plan

What is left to finish V2 and the thesis's experiments, in order. The questions
themselves are in [Open items](open.md), the one list of everything open or decided;
this page only says in which order they are taken and what settles them. The reasons
for decisions are in the [decision log](decisions.md).

## Where the work stands

The workflow runs end to end: the market on SimBench with an AC power flow, both grid
methods, PPO with the mixed action in three paradigms, the runner, the held-out
evaluation and the Studio. The learner is ready for the market by the probe criteria
(RP-2a), and PPO's settings are chosen (RP-6b). Missing: a scenario in which the grid
matters, and evidence that PPO learns the market.

## The order

Each step names the sections of [Open items](open.md) it settles and the check that
settles them. One step at a time; a question that belongs to a later step goes into
the list and waits.

### 1. A scenario in which the grid matters

On SimBench's networks no fee is charged, so the grid-method comparison would show
nothing. **Check, without learning:** a stress level (MP-4i) × the policies `zero`,
`net_position` and the ceiling's plan × both grid methods: line and transformer
loading, voltages, and how often each fee is charged. The level where `net_position`
without fees violates some hours but not all is the comparison's scenario. With it:
the graph model's parameters (MP-4e, the total capacity calibrated against the power
flow), the fee values (MP-4f), then the value of stored energy at midnight (MP-1c) and
the peer charge (MP-4h). Settles section 1. The expected result is written down
before the check runs.

### 2. First learning on the market

Does PPO learn the stressed market, and which action part stops it? **Check:** DTDE as
the control (no grouping, no central critic), one seed, a budget long enough for the
held-out bill to level off, against `zero`, `net_position` and the ceiling. If it does
not beat `net_position`, learn one more action part per rung, the others fixed by the
rule:

| Rung | Learned | Fixed |
|---|---|---|
| A | quantity, price | side from the sign of the net position, no partner |
| B | + side | no partner |
| C | + partner | nothing: the full action |

The rung at which the result drops names the obstacle, and is a result in itself (what
each part of [P1] eq. 2 costs to learn). Settles RP-1a, RP-1h, RP-5a and RP-5b; then the
budget and the settings for every paradigm (RP-6a, L-14), and whichever of RP-3a to
RP-3g the runs show matter. The rest of section 2 is settled on paper along the way.

### 3. The evaluation protocol

Section 3, mostly on paper: how runs are compared (L-03), seeds (L-17), CTCE's role
(L-02), the CTDE critic (L-01), the days (RP-7c). Before the final runs.

### 4. The final runs

The three paradigms on the market, then the grid-method comparison
([Grid methods experiment](../experiments/thesis/grid-methods.md)), every arm with all
seeds, then the analysis.

### Alongside

Section 4 only if the reward and observation experiment
([Reward and observation](../experiments/thesis/reward-obs.md)) stays in the thesis;
section 5 whenever there is time.

## How a question is taken

1. A question noticed anywhere (a `# OPEN` or `# !` in the code, a review note, a
   conversation) goes into [Open items](open.md), in its section, as `inbox` or
   `open`.
2. When its step comes, run the check that informs it.
3. Implement the choice; the docstring names the ID; the commit message names it too.
4. Set its status in [Open items](open.md) to `decided → what was chosen (link)`. A
   choice whose reason needs more than a line gets a row in the
   [decision log](decisions.md).
5. Update the full cycle's phase card: the ID moves from *Open* to **Decisions**.

**Markers in the code.** An open question is `# OPEN <ID>: question`, and its ID must
be in [Open items](open.md) (`tests/test_open_markers.py` checks it). A quick reminder
without an ID is `# ! note`, triaged into the list at the end of a session. When the
question is decided, `OPEN` becomes `# DEVIATION <ID>` if the choice departs from the
paper, and is removed otherwise.

**Where things live.** What the code does now: [the full cycle](../methodology/full-cycle.md)
and its pages. What was wrong in the original: the
[issue register](../original/issues/register.md). What is undecided or decided:
[Open items](open.md). Why: the [decision log](decisions.md).
