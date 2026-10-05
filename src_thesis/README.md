# Standalone thesis implementation

`src_thesis/` is the paper-aligned refactoring of MARLEM and the single source
of truth of this repository. The upstream `src/` package and the frozen copy
`src_thesis_reference/` were removed on 2026-10-03; both remain in the git tag
`marlem-original` (`git show marlem-original:src/<path>`). The path map below
says where each upstream module lives now.

```text
src_thesis/
|-- core/                        # Shared records and protocols; imports nothing else
|   |-- orders.py                # Order, Trade
|   |-- results.py               # MatchingResult, MatchingHistory
|   |-- location.py              # GridTopology, Location
|   |-- interfaces.py            # Participant, BatteryView, GridView, MarketBounds
|   |-- numerics.py              # RLProtection (clipping to safe ranges)
|   `-- grid_contract.py         # records shared with the SimBench grid adapter
|-- agents/                      # Level 1 participants: DERAgent, Battery      -> core
|-- marketplace/                 # Level 0 market: matching, mechanisms,
|   |-- market/                  #   validation, reputation                      -> core
|   `-- dso/                     #   DSO agent                                   -> core
|-- cooperation/                 # Level 2: implicit cooperation, metrics, plots -> core
|-- adapters/                    # Infrastructure                                -> core
|   |-- grid/                    #   NetworkX GridNetwork + GridConfig, SimBench adapter,
|   |                            #   participant placement
|   `-- profiles/                #   CSV and synthetic profile handlers
|-- environment/                 # LocalEnergyMarket and its action, observation, reward
|                                #   and config handlers: the one place that wires
|                                #   concrete agents, grid, DSO and profiles together
|-- marl/                        # RLlib trainer, CTCE/CTDE modules, inference; reaches
|                                #   the environment only when it is the chosen one
|-- rl_testbench/                # reference tasks trained through marl/
|-- experiments/                 # Experiment files, runs, store and workers (docs 03)
|-- application/                 # UI/CLI-facing services (docs 04)
|-- studio/                      # NiceGUI Studio; imports only application/ (docs 05)
`-- root.py
```

Dependencies point one way. `core/` imports nothing else from `src_thesis`;
`agents/`, `marketplace/`, `cooperation/` and `adapters/` import only `core/`
(and themselves); only `environment/` combines them. Components see each other
through the protocols in `core/interfaces.py` (a participant, a grid, the market
bounds), so each can be tested with small stand-ins instead of a whole
environment. `tests/test_studio_boundaries.py` enforces these rules.

The restructure (2026-10-05) moved code without changing behaviour:
`tests/test_golden_episode.py` replays fixed-seed episodes recorded before it.
The original code with the validation markers, at the lines the validation
documents cite, is git tag `marlem-annotated`.

The Studio and CLI call `application/`; only the worker process
(`experiments/worker/`) runs long simulations or Ray. The future UI belongs in a
separate presentation package and should not import grid adapters directly.

## Original-to-thesis path map

The parent folders express architectural ownership; the script basename always
identifies the corresponding original module.

| Original location | Thesis location |
|---|---|
| `src/environment/lem.py` | `src_thesis/environment/lem.py` |
| `src/environment/{action,observation,reward,io}.py` | `src_thesis/environment/` with the same filename |
| `src/environment/{base,ctce,ctde,train,inference}.py` | `src_thesis/marl/` with the same filename (`RLProtection` from `base.py`: `core/numerics.py`) |
| `src/agent/*.py` | `src_thesis/agents/` with the same filename |
| `src/market/order.py` | `src_thesis/core/orders.py` |
| `src/market/{mechanism,matching,reputation,validation}.py` | `src_thesis/marketplace/market/` with the same filename (`MatchingResult`, `MatchingHistory` from `matching.py`: `core/results.py`) |
| `src/market/dso.py` | `src_thesis/marketplace/dso/dso.py` |
| `src/grid/base.py` | `src_thesis/core/location.py` |
| `src/grid/config.py` | `src_thesis/adapters/grid/config.py` |
| `src/grid/network.py` | `src_thesis/adapters/grid/network.py` |
| `src/coordination/implicit_cooperation.py` | `src_thesis/cooperation/implicit_cooperation.py` |
| `src/analytics/*.py` | `src_thesis/cooperation/metrics/` with the same filename |
| `src/visualization/plotter.py` | `src_thesis/cooperation/visualization/plotter.py` |
| `src/profile/*.py` | `src_thesis/adapters/profiles/` with the same filename |
| `src/root.py` | `src_thesis/root.py` |
