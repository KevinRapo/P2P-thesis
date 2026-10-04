# Standalone thesis implementation

`src_thesis/` is the paper-aligned refactoring of MARLEM and the single source
of truth of this repository. The upstream `src/` package and the frozen copy
`src_thesis_reference/` were removed on 2026-10-03; both remain in the git tag
`marlem-original` (`git show marlem-original:src/<path>`). The path map below
says where each upstream module lives now.

```text
src_thesis/
|-- marketplace/                 # Level 0: marketplace and environment
|   |-- lem.py                   # LocalEnergyMarket orchestration
|   |-- action.py
|   |-- observation.py
|   |-- reward.py
|   |-- io.py
|   |-- market/                  # Original market script names
|   |-- dso/                     # DSO market role
|   `-- grid/                    # Grid-domain models and legacy configuration
|-- marl/                        # Level 1: agents and RL integration
|   |-- agents/
|   |-- train.py
|   |-- inference.py
|   |-- base.py
|   |-- ctce.py
|   `-- ctde.py
|-- cooperation/                 # Level 2: cooperation and analysis
|   |-- implicit_cooperation.py
|   |-- metrics/
|   `-- visualization/
|-- adapters/                    # Replaceable infrastructure implementations
|   |-- grid/network.py
|   `-- profiles/
|-- application/                 # UI/CLI-facing services (no MARLEM runtime imports)
|   |-- contracts.py             # service protocols
|   |-- models.py                # returned data (Pydantic)
|   |-- demo.py                  # demo services with sample data
|   `-- container.py             # build_services("demo")
|-- studio/                      # NiceGUI Studio; imports only application/
|   |-- app.py, __main__.py
|   |-- layout.py, navigation.py, theme.py, state.py
|   |-- components/
|   `-- pages/
|-- experiments/                 # Experiment files, runs, store and workers (docs 03)
|   |-- models/                  # records, files, expand, resolve, manifest
|   |-- factory/                 # environment and RLlib configuration
|   |-- store/                   # run folders, step recorder
|   `-- worker/                  # runners, worker process, pool
`-- root.py
```

Each inherited script keeps its original filename even when its parent package
has moved. Package `__init__.py` files do not provide compatibility wrappers.

The inherited grid behavior currently lives in
`adapters/grid/network.py`. Market code still calls concrete legacy grid
operations, so the next architectural step is to define a grid contract and
redirect those consumers before introducing SimBench.

The Studio and CLI call `application/`; only the worker process
(`experiments/worker/`) runs long simulations or Ray. The future UI belongs in a
separate presentation package and should not import grid adapters directly.

## Original-to-thesis path map

The parent folders express architectural ownership; the script basename always
identifies the corresponding original module.

| Original location | Thesis location |
|---|---|
| `src/environment/lem.py` | `src_thesis/marketplace/lem.py` |
| `src/environment/{action,observation,reward,io}.py` | `src_thesis/marketplace/` with the same filename |
| `src/environment/{base,ctce,ctde,train,inference}.py` | `src_thesis/marl/` with the same filename |
| `src/agent/*.py` | `src_thesis/marl/agents/` with the same filename |
| `src/market/{order,mechanism,matching,reputation,validation}.py` | `src_thesis/marketplace/market/` with the same filename |
| `src/market/dso.py` | `src_thesis/marketplace/dso/dso.py` |
| `src/grid/{base,config}.py` | `src_thesis/marketplace/grid/` with the same filename |
| `src/grid/network.py` | `src_thesis/adapters/grid/network.py` |
| `src/coordination/implicit_cooperation.py` | `src_thesis/cooperation/implicit_cooperation.py` |
| `src/analytics/*.py` | `src_thesis/cooperation/metrics/` with the same filename |
| `src/visualization/plotter.py` | `src_thesis/cooperation/visualization/plotter.py` |
| `src/profile/*.py` | `src_thesis/adapters/profiles/` with the same filename |
| `src/root.py` | `src_thesis/root.py` |
