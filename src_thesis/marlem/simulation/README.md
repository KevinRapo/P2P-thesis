# marlem/simulation: play a day

Everything needed to run one simulated day on the original market, watch what the
network does and check that it behaved. Used by the Studio's Simulate and Validate
pages (through `platform/kernel/` runners) and by tests.

## One step

```
controllers.py   views -> Intent per agent         (policy.py: AgentView, Intent)
lem_engine.py    intents -> LocalEnergyMarket step  (spec.py: StepOutcome)
settlement.py    outcome -> what each agent physically did (spec.py: Settlement)
injection.py     settlements -> kW at each bus      (grid/contract.py: ParticipantInjection)
grid/simbench.py SimBenchGrid.assess -> GridAssessment (one power flow)
checks.py        outcome + settlement + assessment -> findings
loop.py          run_simulation(): the loop over steps, records, callbacks
scenarios.py     fixture days with an expected network response
```

## Files

| File | Role | Plain data (UI may import) |
|---|---|---|
| `spec.py` | `EngineSpec`, `AgentSpec`, `StepOutcome`, `Settlement`, the `MarketEngine` protocol | yes |
| `policy.py` | `AgentView`, `Intent`, `Policy` protocol | yes |
| `checks.py` | check catalogue, `check_step`, `check_day`, `summarize` | yes |
| `catalog.py` | controller and scenario descriptions for the UI | yes |
| `controllers.py` | `NoOrder`, `RandomOrders`, `NetPosition`, `get_policy` | no |
| `lem_engine.py` | the original market behind `MarketEngine`; `build_engine` | no |
| `fixed_profiles.py` | profile handler that keeps the profiles it was given (I-05) | no |
| `settlement.py`, `injection.py` | step outcome to physical flows to grid injections | no |
| `loop.py` | `run_simulation` | no |
| `scenarios.py` | sanity scenarios and their expectations | no |

`__init__.py` stays import-free so the plain-data modules can be imported without
loading the simulator (tested in `tests/test_package_boundaries.py`).

## Where it is used

Platform side: `platform/experiments/runners/simulate.py` (runs a day in a worker),
`runners/probe.py` (dry run, scenarios in a subprocess), `factory/environment.py`
(experiment file to `EngineSpec`). Documentation: `docs_thesis/thesis/architecture/06-code-organisation.md`.
