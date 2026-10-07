# About these docs

## Source and build

The Markdown source is `docs/` in the repository, readable on its own in VS Code
and on GitHub. The site is built with MkDocs Material from `docs_site/`:

```text
pip install -r docs_site/requirements.txt        # once, in the marlem env
mkdocs serve -f docs_site/mkdocs.yml -a 127.0.0.1:8001   # live preview
mkdocs build -f docs_site/mkdocs.yml             # static site in site/
```

`run_all.py docs-clean` starts the preview at http://127.0.0.1:8001. A new document appears on the site once it is added
to `nav` in `docs_site/mkdocs.yml`. After editing `docs_site/hooks.py`, restart
`mkdocs serve`; changes to the docs, the code and `docs_site/overrides/` are
picked up while it runs.

What the site does differently from the Markdown files happens at build time in
`docs_site/hooks.py`: it generates the API pages, and turns links to code and
other non-Markdown files into links to the repository on GitHub, keeping `#L` line
anchors. Those links point at the `clean` branch, so they work once it is pushed.

## The API reference

The API pages are generated from the code, never written by hand:

- **One section per top-level folder** (`grid`, `market`, `config`,
  `services`, `studio`), in `API_SECTIONS` in `docs_site/hooks.py`. A package
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
