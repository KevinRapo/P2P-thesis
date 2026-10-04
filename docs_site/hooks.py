"""Build-time changes that turn docs_thesis/ into a website, without touching it.

- Generated pages that only exist on the site: the home page, the MathJax
  configuration and the API reference: one page per module, grouped into
  sections and packages (``API_SECTIONS``), built into the nav at "API Reference".
- The generated "Contents" blocks and "↑ Contents" links are removed: the site
  shows its own table of contents on every page.
- Links to code and other non-Markdown files become links to the repository on
  GitHub, with their line anchors (``#L12-L20``) kept. The site does not serve
  source files, and ``#L`` anchors are a GitHub feature.
"""

from __future__ import annotations

import ast
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
| **Guide** | [Studio workflow](guide/studio-workflow.md): how to use the Studio, from the first launch to comparing runs. |
| **Papers** | [Methodology](paper/marlem-methodology.md): what the papers say. [Paper-to-code map](paper/marlem-paper-to-code-map.md): where each part lives in the original code. |
| **Validation** | [How the validation docs work](thesis/validation/README.md), then the [issue register](thesis/validation/issues.md). |
| **Architecture** | [Master document](thesis/architecture/README.md): goal, roadmap, decision log. |
| **API Reference** | [One page per module](api/index.md) of `src_thesis/`, generated from the docstrings: MARLEM by paper level, the adapters, and the platform layers. |

The Markdown source is `docs_thesis/` in the repository; this site is built from
it with `mkdocs build -f docs_site/mkdocs.yml`.
"""

MATHJAX = """window.MathJax = {
  tex: {inlineMath: [["\\\\(", "\\\\)"]], displayMath: [["\\\\[", "\\\\]"]],
        processEscapes: true, processEnvironments: true},
  options: {ignoreHtmlClass: ".*|", processHtmlClass: "arithmatex"}
};
document$.subscribe(() => { MathJax.typesetPromise && MathJax.typesetPromise() })
"""

# The API reference: one section per layer, one page per module. A source is a
# package (documented recursively: subpackages become subsections) or a module.
API_NAV_TITLE = "API Reference"
API_SECTIONS = [
    # MARLEM itself, by the paper's levels ([P1] Fig. 2).
    (
        "Level 0: marketplace",
        "marketplace",
        ["src_thesis.marketplace"],
        "paper/marlem-paper-to-code-map.md",
    ),
    (
        "Level 1: MARL",
        "marl",
        ["src_thesis.marl"],
        "paper/marlem-paper-to-code-map.md",
    ),
    (
        "Level 2: cooperation",
        "cooperation",
        ["src_thesis.cooperation"],
        "paper/marlem-paper-to-code-map.md",
    ),
    (
        "Adapters",
        "adapters",
        ["src_thesis.adapters"],
        "thesis/architecture/01-simbench-grid.md",
    ),
    # The platform around it, bottom-up (architecture README §2.1).
    (
        "Experiment layer",
        "experiments",
        ["src_thesis.experiments"],
        "thesis/architecture/03-experiment-layer.md",
    ),
    (
        "Application layer",
        "application",
        ["src_thesis.application"],
        "thesis/architecture/04-application-layer.md",
    ),
    (
        "Studio",
        "studio",
        ["src_thesis.studio"],
        "thesis/architecture/05-presentation.md",
    ),
]
_API_PAGES: dict[str, str] = {}


def _summary(path: Path) -> str:
    """First line of a module's docstring."""
    try:
        doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8")))
    except (OSError, SyntaxError):
        return ""
    return (doc or "").strip().splitlines()[0] if doc else ""


def _source(repo: Path, dotted: str) -> Path:
    base = repo / Path(*dotted.split("."))
    return base / "__init__.py" if base.is_dir() else base.with_suffix(".py")


def _module_page(dotted: str, repo: Path, links: dict) -> str:
    rel = _source(repo, dotted).relative_to(repo).as_posix()
    url = f"{links['repo']}/blob/{links['ref']}/{rel}"
    return "\n".join(
        [
            f"# {dotted.rsplit('.', 1)[-1]}",
            "",
            f"`{dotted}` · [source on GitHub]({url})",
            "",
            f"::: {dotted}",
            "    options:",
            "      show_root_heading: false",
            "      heading_level: 2",
            "",
        ]
    )


def _table(rows: list[tuple[str, str, str]]) -> list[str]:
    lines = ["| Module | Summary |", "|---|---|"]
    lines += [f"| [`{name}`]({link}) | {text} |" for name, link, text in rows]
    return lines + [""]


def _package(dotted: str, page_dir: str, repo: Path, links: dict) -> tuple:
    """Pages and nav for a package: an index page, its modules, its subpackages."""
    folder = repo / Path(*dotted.split("."))
    modules = sorted(p.stem for p in folder.glob("*.py") if not p.stem.startswith("_"))
    subpackages = sorted(
        d.name
        for d in folder.iterdir()
        if d.is_dir() and (d / "__init__.py").exists() and not d.name.startswith("_")
    )
    pages: dict[str, str] = {}
    nav: list = [f"{page_dir}/index.md"]
    rows = []
    for name in subpackages:
        sub_pages, sub_nav = _package(
            f"{dotted}.{name}", f"{page_dir}/{name}", repo, links
        )
        pages.update(sub_pages)
        nav.append({name: sub_nav})
        rows.append(
            (f"{name}/", f"{name}/index.md", _summary(folder / name / "__init__.py"))
        )
    for name in modules:
        path = f"{page_dir}/{name}.md"
        pages[path] = _module_page(f"{dotted}.{name}", repo, links)
        nav.append({name: path})
        rows.append((name, f"{name}.md", _summary(folder / f"{name}.py")))
    index = [
        f"# {dotted.rsplit('.', 1)[-1]}",
        "",
        f"`{dotted}`",
        "",
        f"::: {dotted}",
        "    options:",
        "      show_root_heading: false",
        "      members: false",
        "",
        *_table(rows),
    ]
    pages[f"{page_dir}/index.md"] = "\n".join(index)
    return pages, nav


def _design(doc: str, up: str) -> str:
    return f"Design and reasons: [{doc.rsplit('/', 1)[-1]}]({up}{doc})."


def _api(repo: Path, links: dict) -> tuple[dict[str, str], list]:
    pages: dict[str, str] = {}
    nav: list = ["api/index.md"]
    overview = [
        "# API Reference",
        "",
        "Generated from the docstrings of `src_thesis/`,"
        " one page per module. Why each module exists and how the parts work"
        " together is in the architecture document linked from each section.",
        "",
        "| Section | Contents | Design |",
        "|---|---|---|",
    ]
    for title, slug, sources, doc in API_SECTIONS:
        root = f"api/{slug}"
        first = repo / Path(*sources[0].split("."))
        if len(sources) == 1 and first.is_dir():
            # The section is one package: its index page is the section page.
            sub_pages, section_nav = _package(sources[0], root, repo, links)
            pages.update(sub_pages)
            index = pages[f"{root}/index.md"].split("\n")
            index[0] = f"# {title}"
            index[1:1] = ["", _design(doc, "../../")]
            pages[f"{root}/index.md"] = "\n".join(index)
        else:
            section_nav = [f"{root}/index.md"]
            rows = []
            for dotted in sources:
                name = dotted.rsplit(".", 1)[-1]
                if (repo / Path(*dotted.split("."))).is_dir():
                    sub_pages, sub_nav = _package(dotted, f"{root}/{name}", repo, links)
                    pages.update(sub_pages)
                    section_nav.append({name: sub_nav})
                    link = f"{name}/index.md"
                else:
                    pages[f"{root}/{name}.md"] = _module_page(dotted, repo, links)
                    section_nav.append({name: f"{root}/{name}.md"})
                    link = f"{name}.md"
                rows.append((dotted, link, _summary(_source(repo, dotted))))
            pages[f"{root}/index.md"] = "\n".join(
                [f"# {title}", "", _design(doc, "../../"), ""] + _table(rows)
            )
        nav.append({title: section_nav})
        names = ", ".join(f"`{d}`" for d in sources)
        overview.append(
            f"| [{title}]({slug}/index.md) | {names} | {_design(doc, '../')} |"
        )
    pages["api/index.md"] = "\n".join(overview) + "\n"
    return pages, nav


def on_config(config):
    """Build the API pages and put their tree into the nav under API_NAV_TITLE."""
    global _API_PAGES
    repo = Path(config.config_file_path).resolve().parent.parent
    _API_PAGES, api_nav = _api(repo, config["extra"]["code_links"])
    for i, item in enumerate(config["nav"]):
        if isinstance(item, dict) and API_NAV_TITLE in item:
            config["nav"][i] = {API_NAV_TITLE: api_nav}
    return config


def on_files(files, config):
    generated = {"index.md": HOME, "javascripts/mathjax.js": MATHJAX, **_API_PAGES}
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
