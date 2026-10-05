# 1. Experiment input

[Master overview](README.md) · [Next: participants](02-participants.md)

## Why this stage exists

The experiment file makes a study explicit: network, participants, time periods,
market rules, learning settings and requested outputs. It is configuration data;
it does not contain a running grid, a policy or live Python agents.

## What goes in and comes out

Input: a preset/library ID or experiment JSON. Output: an `ExperimentFile` model.
Resolution fills defaults; expansion produces `RunCell` records describing
individual jobs. These are separate operations, not implicit consequences of
loading a file.

For example, the existing heterogeneity preset contains this fragment:

```json
{
  "schema_version": "1.0",
  "kind": "marlem-experiment",
  "grid": {"source": {"type": "simbench", "code": "1-LV-semiurb4--0-sw"}},
  "time": {"resolution": "hourly_aggregated", "horizon_steps": 24}
}
```

This is a fragment, not a complete runnable file. `horizon_steps` requests episode
length; it does not prove the runtime executes the correct number of intervals.
A `RunCell` chooses one algorithm/paradigm/seed or baseline from the study plan.

## Where it happens

| Function / model | What to read it for |
|---|---|
| [ConfigService.load](../../src_thesis/platform/services/config_service.py) | Searches the library and presets and delegates to `files.load` |
| [ExperimentFile](../../src_thesis/platform/kernel/models/records.py) | The typed representation of the study |
| [sections.py](../../src_thesis/platform/kernel/models/sections.py) | Types for its nested sections |
| [ConfigService.resolve / days / expand](../../src_thesis/platform/services/config_service.py) | Separate application operations for defaults, dates and run cells |
| [resolve / resolve_run / resolve_days](../../src_thesis/platform/kernel/models/resolve.py) | Filling defaults, fixing one run and selecting date lists |
| [expand](../../src_thesis/platform/kernel/models/expand.py) | Turning the learning plan and sweeps into cells |

For the complete field specification, use [Experiment configuration](../thesis/architecture/02-experiment-config.md).

## Who calls it

Studio pages obtain their draft through
[`studio.state.current_draft`](../../src_thesis/platform/studio/state.py). It asks
`services().config.load` for the remembered draft, otherwise finds the latest
library draft or creates one from the default preset. `open_draft` saves the file
and remembers its ID in the browser session.

The shared [`shell`](../../src_thesis/platform/studio/layout.py) also calls
`ValidationService.validate(draft, level="schema")` to populate header indicators.
That label must be interpreted in light of the service's current implementation.

## Current status

File loading, saving, default resolution and run expansion have implementations.
This source review did not execute a research run to validate their integration.

[`ValidationService`](../../src_thesis/platform/services/validate/service.py) declares
`SAMPLE_DATA = True`. Its report combines fixed findings with a check for missing
participants. Its `dry_run` returns a sample success without constructing an
environment. Schema parsing and full physical/methodological validation are
different levels of assurance.

**Next:** [2. Participants and profiles](02-participants.md). We now know which
study is open; the next question is what each participant represents.
