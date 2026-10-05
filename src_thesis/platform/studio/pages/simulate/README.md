# Simulate page

Scripted controllers play days on the draft's market and network; the page shows
progress, a step-by-step replay and the checks. Routes: `/simulate`,
`/simulate/{run_id}`.

## Flow

```
studio/pages/simulate/page.py          set up (controller, day, days, seed), Run, watch
   | create run                          | read
   v                                     v
services/simulate/service.py           services/results (ResultService)
   SimulateService.create_simulation      replay, topology, checks, summary
   | RunCell(kind="simulate") -> run folder
   v
services/experiment_service.py         start / cancel / snapshot (worker pool, polled by one timer)
   |
   v  worker process
kernel/simulate/runner.py              SimulateRunner: builds the day, writes raw/steps.jsonl per step
   |
   v
kernel/factory/environment.py          experiment file -> EngineSpec, engine, grid
marlem/simulation/loop.py              run_simulation (see marlem/simulation/README.md)
```

## Files of this page

| File | Role |
|---|---|
| `studio/pages/simulate/page.py` | The page: set-up card, recent runs, live view of one run |
| `services/simulate/service.py`, `models.py` | Controller list and parameters, creating a simulation run |
| `kernel/simulate/runner.py` | The worker side of a simulation run |

## Shared with other pages

- `studio/components/replay.py`, `checks_panel.py`: also used by Results.
- `services/result_service.py`: reads simulation runs for this page and Results.
- `services/experiment_service.py`: starts, cancels and lists runs; also used by Runs.
- `kernel/models/records.py` (`RunCell`): the run's settings.

## Typical changes

- New controller or parameter: `marlem/simulation/controllers.py` and `catalog.py`; the page builds its controls from the catalog.
- New option on the page: `page.py`, `services/simulate/service.py`, `RunCell` in `kernel/models/records.py`, `kernel/simulate/runner.py`.
- New thing shown in the replay: record it in `kernel/simulate/runner.py`, show it in `studio/components/replay.py`.
