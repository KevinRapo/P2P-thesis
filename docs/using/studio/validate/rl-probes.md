# RL probes

**Check the learner on small problems with a known answer**, before trusting it on
the market ([The RL probes](../../../methodology/validation/probes.md)). A probe run is
an ordinary run of an experiment named `probes_<preset>`.

- **The run table:** as on Results ([run table](../experiments/results/index.md#the-run-table)),
  with two more columns: the probe and its result.
- **Tick probe runs** to see a summary: each probe against each paradigm, PASS or
  FAIL with the worst error relative to its tolerance.
- **One probe run at a time:** what the probe tests, its setup, the exact answer,
  what a correct learner shows, the market feature it stands for, and its checks:
  expected against what the trained networks give.

A run without checks shows *not scored*. How any run's training went is on
[Results → Learning](../experiments/results/learning.md).
