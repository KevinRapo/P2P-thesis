"""File graphs of the code folders, generated into the architecture documents.

A block between ``<!-- BEGIN generated:graph KEY -->`` and
``<!-- END generated:graph -->`` is replaced by a Mermaid diagram of how the files
of ``GRAPHS[KEY]`` import each other, read from the code:

- solid arrow: a file imports another file of the same folder;
- dashed arrow: an import of a shared type module (e.g. ``models/records``) that
  nearly every file uses; drawn faintly so the real structure stays visible;
- grey boxes: other packages the folder uses (right) or that use it (left).

    python docs_thesis/graphs.py           # rewrite the blocks
    python docs_thesis/graphs.py --check   # exit 1 if a block is stale (used by tests)
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent
SRC = DOCS.parent / "src_thesis"
ARCH = DOCS / "thesis" / "architecture"

GRAPHS: dict[str, dict] = {
    "grid": {
        "roots": ["adapters/grid/simbench_new.py", "marketplace/grid/contract_new.py"],
    },
    "experiments": {"roots": ["experiments"], "faded": ["experiments/models/records"]},
    "application": {"roots": ["application"], "faded": ["application/models"]},
    "studio": {"roots": ["studio"], "collapse": {"studio/pages/": "studio/pages/*"}},
}
BLOCK = re.compile(
    r"(<!-- BEGIN generated:graph (\w+) -->\n).*?(<!-- END generated:graph -->)",
    re.S,
)


def _files(roots: list[str]) -> list[Path]:
    out = []
    for root in roots:
        path = SRC / root
        found = [path] if path.is_file() else sorted(path.rglob("*.py"))
        out += [p for p in found if p.name != "__init__.py"]
    return out


def _name(path: Path) -> str:
    return path.relative_to(SRC).with_suffix("").as_posix()


def _imports(path: Path) -> set[str]:
    """``src_thesis`` modules imported by ``path``, as ``a/b/c`` names."""
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if node.module.startswith("src_thesis."):
                base = node.module[len("src_thesis.") :].replace(".", "/")
                for alias in node.names:
                    sub = f"{base}/{alias.name}"
                    out.add(sub if (SRC / f"{sub}.py").is_file() else base)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("src_thesis."):
                    out.add(alias.name[len("src_thesis.") :].replace(".", "/"))
    return out


def _collapse(name: str, rules: dict[str, str]) -> str:
    for prefix, target in rules.items():
        if name.startswith(prefix):
            return target
    return name


def _outside(name: str) -> str:
    """Other packages are shown at two levels, e.g. ``experiments/models``."""
    return "/".join(name.split("/")[:2])


def build(key: str) -> str:
    spec = GRAPHS[key]
    rules = spec.get("collapse", {})
    faded = set(spec.get("faded", []))
    own = _files(spec["roots"])
    nodes = {_collapse(_name(p), rules) for p in own}
    edges: set[tuple[str, str, bool]] = set()
    uses: set[str] = set()
    for path in own:
        src = _collapse(_name(path), rules)
        for target in _imports(path):
            dst = _collapse(target, rules)
            if dst in nodes:
                if dst != src:
                    edges.add((src, dst, dst in faded))
            elif not any(dst.startswith(r.removesuffix(".py")) for r in spec["roots"]):
                dst = _outside(dst)
                uses.add(dst)
                edges.add((src, dst, False))
    users: set[str] = set()
    for path in sorted(SRC.rglob("*.py")):
        name = _name(path)
        if _collapse(name, rules) in nodes or path.name == "__init__.py":
            continue
        for target in _imports(path):
            if _collapse(target, rules) in nodes:
                user = name.split("/")[0] + " (users)"
                users.add(user)
                edges.add((user, _collapse(target, rules), False))

    def node_id(name: str) -> str:
        return "n_" + re.sub(r"\W", "_", name)

    single = len(spec["roots"]) == 1 and (SRC / spec["roots"][0]).is_dir()
    prefix = spec["roots"][0] + "/" if single else ""

    def label(name: str) -> str:
        return name[len(prefix) :] if prefix and name.startswith(prefix) else name

    groups: dict[str, list[str]] = {}
    for name in sorted(nodes):
        rel = label(name)
        group = rel.split("/")[0] if "/" in rel and not rel.endswith("*") else ""
        if rel.endswith("/*"):
            group = ""
        groups.setdefault(group, []).append(name)

    lines = ["```mermaid", "flowchart LR"]
    if users:
        lines.append('  subgraph USERS["used by"]')
        lines += [f'    {node_id(u)}["{u.split()[0]}/"]:::ext' for u in sorted(users)]
        lines.append("  end")
    for group, names in groups.items():
        indent = "  "
        if group:
            lines.append(f'  subgraph g_{group}["{group}/"]')
            indent = "    "
        for name in names:
            lines.append(f'{indent}{node_id(name)}["{label(name)}"]')
        if group:
            lines.append("  end")
    if uses:
        lines.append('  subgraph USES["uses"]')
        lines += [f'    {node_id(u)}["{u}"]:::ext' for u in sorted(uses)]
        lines.append("  end")
    for src, dst, fade in sorted(edges):
        arrow = "-.->" if fade else "-->"
        lines.append(f"  {node_id(src)} {arrow} {node_id(dst)}")
    lines.append("  classDef ext fill:#e5e7eb,stroke:#6b7280,color:#111")
    lines.append("```")
    return "\n".join(lines) + "\n"


def render(text: str) -> str:
    return BLOCK.sub(lambda m: m.group(1) + build(m.group(2)) + m.group(3), text)


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    for path in sorted(ARCH.glob("*.md")):
        raw = path.read_bytes()
        crlf = b"\r\n" in raw
        text = raw.decode("utf-8").replace("\r\n", "\n")
        new = render(text)
        if new != text:
            stale.append(path.name)
            if not check:
                data = new.replace("\n", "\r\n") if crlf else new
                path.write_bytes(data.encode("utf-8"))
    for name in stale:
        print(("out of date: " if check else "updated: ") + name)
    return 1 if check and stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
