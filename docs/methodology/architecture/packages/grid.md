# core/grid/: the SimBench network

The only package that imports pandapower and SimBench. It hands out plain records
(`contract.py`), never pandapower objects, so nothing above it depends on them. How
the two grid methods differ: [Grid methods](../../market/grid-methods.md).

```mermaid
%%{init: {"flowchart": {"rankSpacing": 34, "nodeSpacing": 18, "padding": 8}}}%%
flowchart LR
  powerflow["powerflow.py"]:::code --> simbench["simbench.py"]:::code
  powerflow --> contract["contract.py"]:::data
  simbench --> contract
  graphmodel["graph.py"]:::code --> contract

  classDef code fill:#dcfce7,stroke:#15803d,color:#111
  classDef data fill:#dbeafe,stroke:#1d4ed8,color:#111
```

| Module | What it is |
|---|---|
| [`contract`](../../../api/grid/contract.md) | The records that cross the seam: networks, topology, elements, profiles, power-flow results, the path between two buses (`GridPath`) |
| [`simbench`](../../../api/grid/simbench.md) | Listing, loading and caching networks; their topology, elements and profiles; SimBench's study cases |
| [`powerflow`](../../../api/grid/powerflow.md) | `SimBenchGrid`: one AC power flow per market step from what the participants did; the path, distance and zone between two buses |
| [`graph`](../../../api/grid/graph.md) | `GraphGrid`: [P1]'s grid model on the SimBench lines, the line loading from the step's trades, for `grid.method = "graph"` |
