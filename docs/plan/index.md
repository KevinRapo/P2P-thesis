# Plans: finishing the market and the RL layer

Two plans finish V2, in this order:

1. **[The market plan](market.md)**: validate the market step and take its open
   decisions. The market decides what an agent can do and what it is paid for,
   so it is settled first.
2. **[The RL plan](rl.md)**: make PPO with the mixed action learn that market,
   in the three paradigms. It starts from what the market plan hands over.

## Where the work stands

The workflow runs end to end. The learner counts as ready for the market by the
criteria of RP-2a ([probe results](../full-cycle/learning/probes.md#results)), and PPO's training
settings are chosen (RP-6b). What is missing is evidence that PPO learns the market
with the mixed action. The order of the work is in the
[market plan](market.md) and the [RL plan](rl.md), the decisions in the
[decision log](decisions.md). Added on 31 October 2026 and not run yet: longer
training windows, truncation and a terminal value for the battery, compared in
[day_end.json](../../config/experiments/day_end.json) (RP-1f).

## Which page is for what

Each kind of content has exactly one home; the other pages only point to it.

| Page | Holds | Changes when |
|---|---|---|
| [The full cycle](../full-cycle/index.md) and its pages: [market step](../full-cycle/market-step.md), [environment](../full-cycle/environment/index.md), [learning layer](../full-cycle/learning/index.md) | **What the code does now**: every phase of the market step, the environment step and training, with its code, equations and decisions. The reference to read the system from | the code changes |
| [Open items](open.md) | **Everything undecided**: one row per question, with its ID, where it is in the code or the docs, its status and its stage | a question is found, or decided |
| [Market plan](market.md), [RL plan](rl.md) | **What is still to do, in which order**: stages, each with its question, check, the decisions it needs, and a status | a stage starts or ends |
| [Results plan](results.md) | **How results are saved, compared and shown** (RP-7, MP-6a) | stages are done |
| [Decision log](decisions.md) | **What was decided and why**: one row per decision, with its reason, evidence and where it is implemented | a decision is taken |
| [Issue register](../validation/register.md) and the validation pages | **What was wrong in the original**: the evidence the thesis cites. History, not a to-do list | rarely: a status, or a new finding |
| [Overview](../overview.md) | **What this branch does**: its scope and one paragraph per layer | the scope changes |

## Markers: the plans are big, everything else is small

- **The plans carry the work.** Only the plan pages list tasks. They do not
  explain how the market or the learner works; they link to the full cycle for
  that.
- **Every other page carries only IDs.** A plan decision has an ID: `MP-` for the
  market plan, `RP-` for the RL plan, then stage and letter (`MP-1a`, `RP-3b`).
  Elsewhere it appears only as that ID, like the register's `M-19` or `L-03`:
    - in the full cycle, in the phase card's **Decisions** row once decided, or
      as *Open: MP-1a* while it is not;
    - in a docstring of the code that implements it (the same rule as for issue
      IDs, see `AGENTS.md`);
    - in the commit message;
    - in [Open items](open.md), the one list of everything undecided: the plans list
      only the IDs in their stages, never a second copy of the question.
- **Code markers.** An open question in the code is `# OPEN <ID>: question`, and the
  ID must be in [Open items](open.md) (`tests/test_open_markers.py` checks it). A quick
  reminder without an ID is `# ! note`; it is triaged into the list at the end of a
  session. When the question is decided, the `OPEN` becomes `# DEVIATION <ID>` if the
  choice departs from the paper, and is removed otherwise, with the docstring naming
  the ID.

## The loop for one decision

0. A question noticed anywhere (a `# OPEN` or `# !` in the code, a review note, a
   conversation) goes into [Open items](open.md) as `inbox` or `open`.
1. The plan's stage poses it, with the check that informs it.
2. Run the check; write the decision into the [decision log](decisions.md):
   choice, reason, evidence, date.
3. Implement it if it changes code; the docstring names the ID; commit with the
   ID in the message.
4. Update the full cycle's phase card: the ID moves from *Open* to **Decisions**.
   Set the item's status in [Open items](open.md) to `decided → decision log`.
5. When every decision of a stage is in the log and its check passes, set the
   stage's status in the plan to *done (date)*.
