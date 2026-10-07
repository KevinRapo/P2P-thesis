# AGENTS.md: implementation guide for MARLEM clean

MARLEM rebuilt step by step on SimBench networks: configure a local energy market,
then step through it by hand and watch the network's power flow. No reinforcement
learning at this stage.

## Code structure

### Top-level folders

| Folder | Holds |
|---|---|
| `config/` | The scenario the user configures (`Scenario`), and saving and loading it |
| `grid/` | The SimBench network: catalogue, topology, profiles, power flow. The only place that imports pandapower or simbench |
| `market/` | The MARLEM market: orders, matching, pricing, DSO, agents, profiles, and the market step |
| `simulation/` | Stepping a scenario: market step, then power flow, one step at a time |
| `services/` | What the Studio calls. Translates between the Studio's models and `grid/`, `market/` and `simulation/` |
| `studio/` | The NiceGUI Studio: `pages/`, `components/`, layout, theme |
| `docs/` | The documentation, Markdown (see `docs/about.md`) |
| `docs_site/` | The MkDocs site built from `docs/`: config, build hooks, diagram assets |

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
