# 5. Training and evaluation

[Previous: one timestep](04-timestep.md) · [Master overview](README.md)

## Why this stage exists

A policy maps observations to actions. Training changes its parameters using
experience and rewards; evaluation measures the behaviour of a chosen policy.
The market/environment defines the task, while RLlib supplies the learning
machinery configured by MARLEM.

## What goes in and comes out

The existing `RLTrainer` takes an environment class/config and learning settings.
`train()` returns a Ray Tune `ResultGrid` and a metrics dictionary; Tune is also
configured to write checkpoints. A checkpoint stores learned state for later use.

`RLInference` takes a checkpoint plus environment settings. `inference(iters)`
runs episodes and returns metrics. Here `iters` counts inference episodes, whereas
the trainer's stop budget uses training iterations. These units are not equivalent.

For Alice and Bob, the environment computes market outcomes and rewards. RLlib
uses collected experience to update the policy or policies that select their next
offers. A higher shaped reward alone is not proof of a better physical outcome.

## Where it happens

| Entry point | Read it for |
|---|---|
| [RLTrainer._setup_config](../../src_thesis/marlem/marl/train.py) | Algorithm, environment/evaluation and training/model configuration |
| [RLTrainer.train](../../src_thesis/marlem/marl/train.py) | Creates Tune/PBT configuration, calls `tuner.fit`, saves config, extracts metrics and shuts down Ray |
| [GroupedLEM](../../src_thesis/marlem/marl/train.py) | Environment grouping used for centralised configurations |
| [ctce.py](../../src_thesis/marlem/marl/ctce.py), [ctde.py](../../src_thesis/marlem/marl/ctde.py) | Custom RL modules; inspect them alongside the trainer's paradigm branches |
| [RLInference._restore_from_checkpoint / inference](../../src_thesis/marlem/marl/inference.py) | Restores RL module(s), selects actions and loops over environment steps |
| [trainer_arguments](../../src_thesis/platform/experiments/factory/training.py) | Intended experiment-file-to-trainer translation; currently a stub |

CTCE means centralised training and execution; CTDE means centralised training
with decentralised execution; DTDE decentralises both. Those names describe the
intended information/decision arrangement. Correctly implementing each arrangement
must be established by tests, rather than inferred from the class name.

## Who calls it

A direct caller can instantiate `RLTrainer` and call `train`. Inside that method,
`tuner.fit` hands control to Ray/RLlib. Inference is a separate explicit operation
on `RLInference`; it is not the Studio's sample result screen.

The planned platform handoff is `TrainingRunner` → trainer arguments → trainer.
Both [`TrainingRunner.run`](../../src_thesis/platform/experiments/worker/runner.py) and
`trainer_arguments` currently raise `NotImplementedError`. Therefore the Studio
does not provide that working training route yet.

## Current status

Trainer and inference bodies exist, with outstanding issues documented in the
[validation register](../thesis/validation/issues.md). For example, current
`train()` constructs PBT unconditionally; inference manually interprets action
distribution outputs. These are behaviours to validate, not merely presentation details.

The [standalone RL testbench plan](../thesis/validation/rl-testbench.md) is intended
to validate the shared learning path on external tasks. Its
[`evaluate` and `random_baseline`](../../src_thesis/platform/testbench/evaluation.py)
currently raise `NotImplementedError`. This chapter claims no successful learning
or checkpoint-equivalence result.

**Next:** [6. Runs and results](06-results.md). We distinguish existing storage
infrastructure from simulated progress/results displayed by the Studio.
