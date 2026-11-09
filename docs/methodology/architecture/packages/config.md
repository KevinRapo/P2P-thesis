# core/config/: the scenario

Everything the user sets before the market runs, as plain data: the network and the
day, the participants and their batteries, the market rules and the DSO. Every
setting is described in [Config](../../../using/running/config.md).

| Module | What it is |
|---|---|
| [`scenario`](../../../api/config/scenario.md) | `Scenario` and its parts (`GridSetup`, `ParticipantSetup`, `BatterySetup`, `MarketSetup`, `DsoSetup`); each part lists its own problems (`problems()`), which the Studio's Summary shows |
| [`store`](../../../api/config/store.md) | Saving and loading a scenario as JSON |
| [`placement`](../../../api/config/placement.md) | Placing participants on the network's buses, and SimBench-sized batteries; uses `core/grid/` |
