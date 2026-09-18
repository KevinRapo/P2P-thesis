# Training-time benchmarks

The current Case 6 notebook uses the original repository's RLlib iteration
budget (`TRAINING_EPISODES=10000`) across its 3x3 matrix. An iteration is not a
universal episode or environment-step unit: PPO, APPO, and SAC stop each
iteration at their own sampling/update boundaries. The notebook keeps one Ray
lifecycle across the matrix and records sampled-step/episode counters beside
the requested iteration count. `MARLEM_RESULTS_PATH` and
`MARLEM_RAY_TEMP_DIR` can place results and Ray temporary state outside
OneDrive. These are execution settings; policy architecture and optimizer
semantics are unchanged.

Measured 2026-09-08 using a direct `RLTrainer` timing harness (not the notebooks themselves — no kernel/kernel-startup overhead, cleaner numbers). Machine: 6 cores / 12 logical processors, CPU-only (`cpus=1, gpus=0` for the harness). Reported "marginal" cost separates one-time construction/Ray-startup overhead from the true per-iteration cost, by timing the same config at 1 iteration and again at 3–4 iterations and solving for the linear terms — this is what actually extrapolates to a longer run, unlike a single raw wall-clock number.

## At `case6`'s actual scenario (8 agents, real profile CSVs, IEEE34 grid)

| Algorithm / mode | Marginal cost / iteration | One-time setup |
|---|---|---|
| PPO / DTDE | ~117s | ~32s |
| PPO / CTDE | ~59s | ~38s |

DTDE trains a separate policy per agent, so it costs roughly 2× CTDE's single shared/grouped policy. APPO, SAC, and CTCE were not measured at this scenario size.

## Agent-count scaling (lighter synthetic scenario, PPO/DTDE only)

| Agents | Marginal cost / iteration |
|---|---|
| 5 | ~50s |
| 10 | ~90s |
| 20 | ~205s |
| 40 | >430s (measured: 518s for one-time setup + first iteration combined, not yet separated) |

The cost-per-doubling ratio accelerates (1.8× → 2.3× → >2.5×) rather than staying flat at 2×, consistent with roughly O(n²) cost in the market-clearing step (pairwise buyer/seller matching). 80+ agents was never measured but extrapolates to likely 15–30+ minutes per iteration — probably impractical on this machine as currently configured.

## Practical implications

- A 10,000-iteration Case 6 matrix is not a practical overnight run on this
  hardware: the measured iteration costs imply many days once all nine
  combinations are included. Use a reduced iteration count for execution
  checks, then budget the full original protocol from a measured one-iteration
  rate for each algorithm/mode.
- `case7`'s committed default sweeps 54 agent-population × mode × algorithm combinations — also not viable at full scale on this hardware in one sitting.
- Before proposing or running a real (non-zero-intelligence) training pass on
  any notebook, sanity-check the requested population size and iteration count
  against the numbers above. If it would take many hours or days, say so
  explicitly and use a reduced scale for a first pass.

## CPU allocation

The current Case 6 notebook uses `CPUS=6, GPUS=0`, which maps to six RLlib
environment runners. The table above is a one-runner reference, so remeasure
`cpus=4`, `6`, and `8` on the target machine before a long sweep; more runners
can hurt once process and serialization overhead dominate.

## Runtime lifecycle

The Case 6 notebook reuses one Ray lifecycle across its matrix and shuts it
down in a final cleanup block, with no fixed sleep or cooldown in the protocol.
Standalone benchmark scripts should use the same lifecycle pattern (or shut
Ray down explicitly after each isolated run) and place Ray temporary files on
a local, non-OneDrive path.
