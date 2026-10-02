"""Build-time changes that turn docs_thesis/ into a website, without touching it.

- Generated pages that only exist on the site: the home page, the API reference
  (mkdocstrings) and the MathJax configuration.
- The generated "Contents" blocks and "↑ Contents" links are removed: the site
  shows its own table of contents on every page.
- Links to code and other non-Markdown files become links to the repository on
  GitHub, with their line anchors (``#L12-L20``) kept. The site does not serve
  source files, and ``#L`` anchors are a GitHub feature.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

from mkdocs.structure.files import File

TOC_BLOCK = re.compile(
    r"^<!-- BEGIN toc \(python docs_thesis/toc\.py\) -->\n.*?^<!-- END toc -->\n\n?",
    re.M | re.S,
)
BACK_LINK = re.compile(r"^\[↑ Contents\]\(#contents\)\n\n?", re.M)
LINK = re.compile(r"\]\(([^)\s]+)\)")
FENCE = re.compile(r"^```.*?^```", re.M | re.S)
SERVED = {".md", ".pdf", ".png", ".jpg", ".jpeg", ".svg", ".gif"}

HOME = """# MARLEM thesis documentation

Validation of the original MARLEM against its papers, and the plan and code of
the SimBench rebuild.

| Section | Start with |
|---|---|
| **Papers** | [Methodology](paper/marlem-methodology.md): what the papers say. [Paper-to-code map](paper/marlem-paper-to-code-map.md): where each part lives in the original code. |
| **Validation** | [How the validation docs work](thesis/validation/README.md), then the [issue register](thesis/validation/issues.md). |
| **Architecture** | [Master document](thesis/architecture/README.md): goal, roadmap, decision log. |
| **API** | Generated from the docstrings of the [experiment layer](api/experiments.md) and the [application layer](api/application.md). |

The Markdown source is `docs_thesis/` in the repository; this site is built from
it with `mkdocs build -f docs_site/mkdocs.yml`.
"""

API = {
    "api/experiments.md": (
        "Experiment layer API",
        "src_thesis/experiments",
        [
            "models.records",
            "models.files",
            "models.expand",
            "models.resolve",
            "models.manifest",
            "store.filesystem",
            "store.recorder",
            "factory.environment",
            "factory.training",
            "worker.runner",
            "worker.process",
            "worker.pool",
        ],
        "thesis/architecture/05-experiment-layer.md",
    ),
    "api/application.md": (
        "Application layer API",
        "src_thesis/application",
        [
            "contracts",
            "container",
            "workspace",
            "config_files",
            "grid_catalog",
            "models",
        ],
        "thesis/architecture/03-application-layer.md",
    ),
}

MATHJAX = """window.MathJax = {
  tex: {inlineMath: [["\\\\(", "\\\\)"]], displayMath: [["\\\\[", "\\\\]"]],
        processEscapes: true, processEnvironments: true},
  options: {ignoreHtmlClass: ".*|", processHtmlClass: "arithmatex"}
};
document$.subscribe(() => { MathJax.typesetPromise && MathJax.typesetPromise() })
"""


def _api_page(title: str, package: str, modules: list[str], doc: str) -> str:
    dotted = package.replace("/", ".")
    body = [
        f"# {title}",
        "",
        f"Generated from the docstrings in `{package}/`. The design and the"
        f" reasons behind each module are in [the architecture document](../{doc}).",
        "",
    ]
    for module in modules:
        body += [f"::: {dotted}.{module}", ""]
    return "\n".join(body)


def on_files(files, config):
    generated = {"index.md": HOME, "javascripts/mathjax.js": MATHJAX}
    for path, (title, package, modules, doc) in API.items():
        generated[path] = _api_page(title, package, modules, doc)
    for path, content in generated.items():
        files.append(File.generated(config, path, content=content))
    return files


def on_page_markdown(markdown, page, config, files):
    markdown = TOC_BLOCK.sub("", markdown.replace("\r\n", "\n"))
    markdown = BACK_LINK.sub("", markdown)
    if page.file.generated_by is not None:
        return markdown
    docs_dir = Path(config["docs_dir"]).resolve()
    repo = docs_dir.parent
    links = config["extra"]["code_links"]
    page_dir = Path(page.file.abs_src_path).parent

    def rewrite(match: re.Match) -> str:
        target = match.group(1)
        if re.match(r"^[a-z]+:|^#", target):
            return match.group(0)
        path, _, anchor = target.partition("#")
        absolute = (page_dir / unquote(path)).resolve()
        inside = absolute.is_relative_to(docs_dir)
        if inside and absolute.is_file() and absolute.suffix.lower() in SERVED:
            return match.group(0)
        if not absolute.is_relative_to(repo):
            return match.group(0)
        kind = "tree" if absolute.is_dir() else "blob"
        rel = absolute.relative_to(repo).as_posix()
        url = f"{links['repo']}/{kind}/{links['ref']}/{rel}"
        return f"]({url}{'#' + anchor if anchor else ''})"

    # Leave fenced code blocks alone.
    parts, last = [], 0
    for fence in FENCE.finditer(markdown):
        parts.append(LINK.sub(rewrite, markdown[last : fence.start()]))
        parts.append(fence.group(0))
        last = fence.end()
    parts.append(LINK.sub(rewrite, markdown[last:]))
    return "".join(parts)
