"""Table of contents and back links for the thesis documents.

Each document gets a ``## Contents`` block (every ``##`` and ``###`` heading)
before its first section, and every ``##`` section ends with a link back to it.
Both are generated; edit the headings, then run:

    python docs/toc.py           # rewrite the documents
    python docs/toc.py --check   # exit 1 if a document is out of date (used by tests)
"""

import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent
FILES = [
    "paper/marlem-methodology.md",
    "paper/marlem-paper-to-code-map.md",
    "thesis/architecture/README.md",
    "thesis/architecture/01-simbench-grid.md",
    "thesis/architecture/02-experiment-config.md",
    "thesis/architecture/03-application-layer.md",
    "thesis/architecture/04-presentation.md",
    "thesis/architecture/05-experiment-layer.md",
    "thesis/validation/README.md",
    "thesis/validation/issues.md",
    "thesis/validation/methodology.md",
    "thesis/validation/plan.md",
    "thesis/validation/marlem-keep-replace-audit.md",
]

BEGIN = "<!-- BEGIN toc (python docs/toc.py) -->"
END = "<!-- END toc -->"
BACK = "[↑ Contents](#contents)"
HEADING = re.compile(r"^(#{2,3}) (.+?)\s*$")


def slug(title: str) -> str:
    """GitHub / VS Code heading anchor."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", title)  # links keep their text
    text = re.sub(r"<[^>]+>", "", text).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def label(title: str) -> str:
    """Heading text for the list: links keep their text only."""
    return re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", title)


def strip_generated(lines: list[str]) -> list[str]:
    """Remove an earlier contents block and the back links."""
    out, skip, removed = [], False, False
    for line in lines:
        if line == BEGIN:
            skip = True
            continue
        if skip:
            skip = line != END
            removed = True
            continue
        if line == BACK:
            removed = True
            continue
        # Drop the blank line a removed part leaves behind.
        if removed and line == "" and out and out[-1] == "":
            continue
        removed = False
        out.append(line)
    return out


def headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """(line index, level, title) of every ## / ### heading outside code fences."""
    found, fence = [], False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        m = None if fence else HEADING.match(line)
        if m and m.group(2) != "Contents":
            found.append((i, len(m.group(1)), m.group(2)))
    return found


def render(text: str) -> str:
    lines = strip_generated(text.split("\n"))
    heads = headings(lines)
    if not heads:
        return text
    seen: dict[str, int] = {}
    toc = [BEGIN, "## Contents", ""]
    for _, level, title in heads:
        anchor = slug(title)
        n = seen.get(anchor, 0)
        seen[anchor] = n + 1
        if n:
            anchor = f"{anchor}-{n}"
        indent = "  " if level == 3 else ""
        toc.append(f"{indent}- [{label(title)}](#{anchor})")
    toc += ["", END, ""]

    tops = [i for i, level, _ in heads if level == 2]
    out: list[str] = []
    for i, line in enumerate(lines):
        if i == tops[0]:
            out += toc
        elif i in tops:
            while out and out[-1] == "":
                out.pop()
            out += ["", BACK, ""]
        out.append(line)
    while out and out[-1] == "":
        out.pop()
    out += ["", BACK, ""]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    for name in FILES:
        path = DOCS / name
        raw = path.read_bytes()
        crlf = b"\r\n" in raw
        text = raw.decode("utf-8").replace("\r\n", "\n")
        new = render(text)
        if new == text:
            continue
        stale.append(name)
        if not check:
            data = new.replace("\n", "\r\n") if crlf else new
            path.write_bytes(data.encode("utf-8"))
    verb = "out of date" if check else "updated"
    for name in stale:
        print(f"{verb}: {name}")
    return 1 if check and stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
