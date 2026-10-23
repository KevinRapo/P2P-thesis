# Plans: finishing the market and the RL layer

Two plans finish V2, in this order:

1. **[The market plan](market.md)**: validate the market step and take its open
   decisions. The market decides what an agent can do and what it is paid for,
   so it is settled first.
2. **[The RL plan](rl.md)**: make PPO with the mixed action learn that market,
   in the three paradigms. It starts from what the market plan hands over.

## Which page is for what

Each kind of content has exactly one home; the other pages only point to it.

| Page | Holds | Changes when |
|---|---|---|
| [The full cycle](../full-cycle.md) | **What the code does now**: every phase of the market step, the environment step and training, with its code, equations and decisions. The reference to read the system from | the code changes |
| [Market plan](market.md), [RL plan](rl.md) | **What is still to do, in which order**: stages, each with its question, check, the decisions it needs, and a status | a stage starts or ends |
| [Decision log](decisions.md) | **What was decided and why**: one row per decision, with its reason, evidence and where it is implemented | a decision is taken |
| [Issue register](../validation/register.md) and the validation pages | **What was wrong in the original**: the evidence the thesis cites. History, not a to-do list | rarely: a status, or a new finding |
| [v2.md](../v2.md) | **What V2 changed from V1**, and its validation runs | V2's scope changes |

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
    - in the commit message.

## The loop for one decision

1. The plan's stage poses it, with the check that informs it.
2. Run the check; write the decision into the [decision log](decisions.md):
   choice, reason, evidence, date.
3. Implement it if it changes code; the docstring names the ID; commit with the
   ID in the message.
4. Update the full cycle's phase card: the ID moves from *Open* to **Decisions**.
5. When every decision of a stage is in the log and its check passes, set the
   stage's status in the plan to *done (date)*.
