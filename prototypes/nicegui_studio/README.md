# MARLEM Studio NiceGUI prototype

This is a small standalone learning application for the proposed MARLEM Studio
architecture. It is deliberately separate from MARLEM’s current runtime and
from the SimBench/pandapower prototype.

It demonstrates a complete, useful first vertical slice:

```text
NiceGUI page
    -> typed GridScenario
    -> StudioService
    -> illustrative grid model
    -> typed GridResult
    -> Plotly chart, metric table, run history, JSON snapshot
```

The model is intentionally not a power-flow solver. Its equations are visible
in `studio/domain.py` and are only there to make the UI interactive while the
architecture is learned. A future SimBench/pandapower adapter can replace
`IllustrativeGridModel` behind `StudioService` without changing the pages.

## Run it

From this folder:

```powershell
uv sync --group dev --link-mode=copy
uv run --no-sync python app.py
```

Open <http://127.0.0.1:8081>.

The prototype runs with NiceGUI development reload enabled. Saving a Python file
reloads the server and refreshes the browser; in-memory demo history and
selection state are reset after that reload.

The OneDrive-safe `--link-mode=copy` avoids hard-link installation issues in
this workspace. Outside OneDrive, ordinary `uv sync --group dev` is sufficient.

Run the tests with:

```powershell
uv run --no-sync pytest -q
```

## What you can do in the UI

- Dashboard: see the application boundary and current session status.
- Grid explorer: change demand, PV generation, and battery discharge; run the
  model; inspect voltage, line loading, transformer loading, losses, and feeder
  exchange; click or box/lasso-select buses in the voltage-profile chart and
  see the selected bus number and pu value in the adjacent table; and save the
  latest result as JSON.
- Run history: inspect all runs created in the current browser/application
  session.

This first version intentionally has no database, worker process, Ray training,
MARLEM imports, or SimBench imports. Those are later milestones from
`docs/architecture.md`, after the service/page boundary is comfortable.

## NiceGUI ideas used here

- `@ui.page` provides explicit page functions for the multi-page shell.
- `ui.navigate.to` moves between pages without a separate frontend.
- `ui.plotly` receives a Plotly figure and updates after a button callback.
- NiceGUI widgets hold the transient form state; `StudioService` owns the
  typed operation and run history.

These patterns follow the current NiceGUI documentation:

- https://nicegui.io/documentation/
- https://nicegui.io/documentation/plotly
- https://nicegui.io/documentation/run
