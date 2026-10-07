# AGENTS.md: implementation guide for MARLEM clean

MARLEM rebuilt step by step on SimBench networks: configure a local energy market,
then step through it by hand and watch the network's power flow. No reinforcement
learning at this stage.

## Current stage: the core first, the Studio later

Right now the work is making sure the market runs correctly on the SimBench
network: `core/`, validated in `notebooks/`. **Do not update `studio/` in
parallel.** Change `core/` and the notebooks only, and leave the Studio as it is
until the user says to bring it up to date, even when a core change leaves a page
behind. Note in the reply what the Studio will need then.

## Code structure

### Three layers

```
core/        the MARLEM functionality: everything a notebook can call
notebooks/   calls core/ only: validates it without the Studio
studio/      the NiceGUI Studio: pages and components on top of adapters/
```

When something looks wrong in the Studio, reproduce it in a notebook first. If
the notebook shows it, the problem is in `core/`; if not, it is in `studio/`.

### Top-level folders

| Folder | Holds |
|---|---|
| `core/` | The core API: the market and its network, callable without any UI |
| `core/config/` | The scenario (`Scenario`), placing participants on its network, saving and loading it |
| `core/grid/` | The SimBench network: catalogue, topology, profiles, power flow. The only place that imports pandapower or simbench |
| `core/market/` | The MARLEM market: orders, matching, pricing, DSO, agents, profiles, and `LocalEnergyMarket` (`lem.py`), the one class that runs a market step and its power flow |
| `notebooks/` | Jupyter notebooks that call `core/` directly to validate it |
| `studio/` | The NiceGUI Studio: `pages/`, `components/`, `adapters/`, layout, theme |
| `studio/adapters/` | What the pages call: a thin layer over `core/` (caching, background threads, the current scenario, the market being played, workspace paths) |
| `docs/` | The documentation, Markdown (see `docs/about.md`) |
| `docs_site/` | The MkDocs site built from `docs/`: config, build hooks, diagram assets |

### Layer rules

- **`core/`** imports nothing from `studio/` or `notebooks/`. Its API is
  `core/grid/contract.py` for the grid, `LocalEnergyMarket` (`core/market/lem.py`)
  for the market, and `Scenario` (`core/config/`) with its rules, e.g. placing
  participants (`core/config/placement.py`). `core/config/` may import
  `core/grid/`, never the reverse. Every rule of the market or the network lives
  here, so a notebook can check it.
- **`notebooks/`** import `core/` only, never `studio/`.
- **`studio/adapters/`** is the Studio's thin layer over the core: caching,
  background threads, the current scenario, the market being played between
  clicks, workspace paths. No domain rules, no records that copy the core's:
  return the core's records as they are. `studio/adapters/models.py` holds only
  what the Studio alone needs (profile classes and types, chart series). Test for
  any logic here: if a notebook would want it too, it belongs in `core/`.
- **`studio/pages/` and `studio/components/`** call `studio/adapters/`. They may
  import the core's plain data records (`StepRecord`, `Trade`, `NetworkRef`,
  `BatterySetup`, `DSO_ID`, the `DESCRIPTIONS` captions) to read and display them,
  but never construct or drive a core engine class. Inside the Studio,
  `MarketService` builds and holds the `LocalEnergyMarket` between clicks; a
  notebook uses `LocalEnergyMarket` directly. A page may name `LocalEnergyMarket`
  as a type (under `TYPE_CHECKING`) to annotate what it reads.

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
