# About these docs

## Source and build

The Markdown source is `docs/` in the repository, readable on its own in VS Code
and on GitHub. The site is built with MkDocs Material, configured in `mkdocs.yml` at
the root; `docs_site/` holds the build hooks, the theme overrides and the
requirements. From the root, in the marlem environment:

```text
pip install -r docs_site/requirements.txt   # once
mkdocs serve                                # live preview, http://127.0.0.1:8001
mkdocs build --strict                       # check and build into site/
python docs_site/export_drawio.py           # after editing a .drawio diagram
```

`python run_all.py docs` also starts the preview, in its own window. The folders
under `docs/` mirror the site: each tab and section is a folder, so a page's place
in the navigation is its place on disk. A new document appears once it is added to
`nav` in `mkdocs.yml`, under its folder's section. After editing `docs_site/hooks.py`, restart
`mkdocs serve`; changes to the docs, the code and `docs_site/overrides/` are
picked up while it runs.

What the site does differently from the Markdown files happens at build time in
`docs_site/hooks.py`: it generates the API pages, and turns links to code and
other non-Markdown files into links to the repository on GitHub, keeping `#L` line
anchors. Those links point at the `marlem-studio` branch, so they work once it is pushed.

## Checking and publishing

Run `mkdocs build --strict` after a change: it stops on broken internal links
and API documentation warnings. The site it builds goes to `site/`, which git
ignores.

The site is public at <https://kevinrapo.github.io/P2P-thesis/>. Every push to `marlem-studio` that changes
`docs/`, `docs_site/`, `mkdocs.yml` or the code behind the API pages (`core/`,
`studio/`) builds it with the same strict check and publishes it
([docs.yml](https://github.com/KevinRapo/P2P-thesis/blob/marlem-studio/.github/workflows/docs.yml));
a build that fails publishes nothing and leaves the previous version online.

## The API reference

The API pages are generated from the code, never written by hand:

- **One section per top-level folder** (`core.grid`, `core.market`,
  `core.config`, `core.env`, `studio`, `core.rl`, `core.runner`), in `API_SECTIONS` in `docs_site/hooks.py`. A package
  becomes a section with an index page; its subpackages become subsections.
- **One page per module**, with its classes and functions, their signatures, type
  annotations and source. The module index lists each module with the **first line
  of its docstring**, so that line should say what the module is for.
- **Private names are hidden**: anything starting with `_` does not appear.
- **Docstrings are Google style** (`Args:`, `Returns:`, `Raises:`,
  `Attributes:`), rendered by mkdocstrings. A class's `__init__` arguments are shown
  with the class. Members appear in source order.
- **A section can link to its design document**: the reasons behind the code
  live in the docs, the API pages say what the code is.

So documenting the code means writing its docstrings well; the API pages follow
on the next build.

## Diagrams

Diagrams are written as Mermaid code blocks (` ```mermaid `) and drawn by
`docs_site/overrides/assets/diagrams.js` instead of Material, which renders them
where they cannot be zoomed. On every diagram:

| Control | Does |
|---|---|
| Drag | pan |
| Ctrl + mouse wheel, or the + / − buttons | zoom |
| Double-click | zoom in |
| fit | back to the whole diagram |
| ⛶ | fill the browser window (Esc closes; F11 as well for the whole screen) |

Diagrams fit themselves again when the window size changes.
`docs_site/overrides/assets/diagrams.css` also widens the page on large screens.

## Formulas

LaTeX between `$…$` (inline) or `$$…$$` (display), rendered by MathJax.
