# AGENTS.md: implementation guide for MARLEM clean

MARLEM rebuilt step by step on SimBench networks: configure a local energy market,
then step through it by hand and watch the network's power flow. No reinforcement
learning at this stage.

## Code structure

### Top-level folders

| Folder | Holds |
|---|---|
| `config/` | The scenario the user configures (`Scenario`), placing participants on its network, saving and loading it |
| `grid/` | The SimBench network: catalogue, topology, profiles, power flow. The only place that imports pandapower or simbench |
| `market/` | The MARLEM market: orders, matching, pricing, DSO, agents, profiles, and `MarketManager` (`manager.py`), the one class that runs a market step and its power flow |
| `services/` | What the Studio calls: a thin adapter (caching, background threads, the current scenario, building the market) over the core |
| `studio/` | The NiceGUI Studio: `pages/`, `components/`, layout, theme |
| `docs/` | The documentation, Markdown (see `docs/about.md`) |
| `docs_site/` | The MkDocs site built from `docs/`: config, build hooks, diagram assets |

### Layer rules

- **Core** is `grid/`, `market/` and `config/`. It imports nothing from `services/` or
  `studio/`. Its API is `grid/contract.py` for the grid, `MarketManager`
  (`market/manager.py`) for the market, and `Scenario` (`config/`) with its rules,
  e.g. placing participants (`config/placement.py`). `config/` may import `grid/`,
  never the reverse.
- **`services/`** is a thin adapter for the Studio: caching, background threads,
  the current scenario, workspace paths. No domain rules, no records that copy the
  core's: return the core's records as they are. `services/models.py` holds only
  what the Studio alone needs (profile classes and types, chart series).
- **`studio/`** calls `services/` only. A page may import the core's plain data
  records (`StepRecord`, `Trade`, `NetworkRef`, `BatterySetup`, `DSO_ID`, the
  `DESCRIPTIONS` captions) to read and display them, but it must not construct or
  drive an engine class. `MarketService` is the only place that builds and holds
  the `MarketManager`; pages call it to build, step and advance. A page may name
  `MarketManager` as a type (under `TYPE_CHECKING`) to annotate what it reads.

Every folder and script, with how far it is built, is in
`docs/structure.md`: update it whenever a file is added, moved, renamed or built.

### Studio: pages and components

- **A page** is one file in `studio/pages/`. Code that only one page uses stays in
  that page's file.
- **A component** goes in `studio/components/` only when it is actually used in
  more than one place. Being in `components/` means "reused", not "could be
  reused someday".
- When a second place needs code that lives in a page, move it to `components/`
  at that moment, not before.

### Sections inside a file

- A file that does more than one thing is split into **sections** with a banner,
  so each part of its functionality is easy to find:

  ```python
  # --------------------------------------------------------------------------------------
  # Catalog: which networks exist and their names
  # --------------------------------------------------------------------------------------
  ```

  The title says what the section is for. Inside a large class, a one-line
  marker groups its methods: `    # --- Network cache ----------…`.
- A file with one purpose (one class, a few lines) needs no sections.
- When adding code, put it in the section it belongs to; when a section grows its
  own purpose, give it its own banner.
