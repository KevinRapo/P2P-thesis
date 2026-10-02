# Docs website

Builds a website from `docs_thesis/` with MkDocs Material. The Markdown source is
not changed: it stays readable in VS Code and on GitHub, and everything the site
needs differently happens at build time in [hooks.py](hooks.py):

- the generated home page, API reference pages (mkdocstrings) and MathJax setup;
- the "Contents" blocks and "↑ Contents" links are removed (the site has its own
  table of contents on every page);
- links to code and other non-Markdown files point to the repository on GitHub
  (`extra.code_links` in [mkdocs.yml](mkdocs.yml)), keeping `#L` line anchors.

Diagrams are drawn by [overrides/assets/diagrams.js](overrides/assets/diagrams.js)
instead of Material (which renders them where they cannot be zoomed): drag to
pan, Ctrl + mouse wheel or the +/− buttons to zoom, double-click to zoom in,
"fit" to reset, ⛶ for full screen. [diagrams.css](overrides/assets/diagrams.css)
also widens the page on large screens.

```text
pip install -r docs_site/requirements.txt        # once, in the marlem env
mkdocs serve -f docs_site/mkdocs.yml             # live preview at http://127.0.0.1:8000
mkdocs build -f docs_site/mkdocs.yml             # static site in site/ (git-ignored)
```

New documents appear on the site once they are added to `nav` in `mkdocs.yml`.
Code links go to the `dev` branch on GitHub, so they show what is pushed there.

To go back to Markdown only, delete this folder and `site/`.
