"""Every ``# OPEN`` marker in the code names an item of docs/temp/open.md.

The marker is ``# OPEN <ID>: question``; the ID is a register ID (``E-10``, ``M-23``,
``L-14``) or a plan ID (``MP-6a``, ``RP-1f``), and open.md lists it in its ID column.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ID = r"[A-Z]{1,2}P?-\d+[a-z]?"
MARKER = re.compile(r"#\s*OPEN\b(.*)")
LEADING_IDS = re.compile(rf"\s*({ID}(?:\s*,\s*{ID})*)\s*:")
FOLDERS = ("core", "studio")


def markers() -> list[tuple[str, int, str]]:
    """(file, line number, text after ``OPEN``) of every marker in the code."""
    found = []

    for folder in FOLDERS:
        for path in sorted((ROOT / folder).rglob("*.py")):
            lines = path.read_text(encoding="utf-8").splitlines()

            for number, line in enumerate(lines, start=1):
                if match := MARKER.search(line):
                    found.append((path.relative_to(ROOT).as_posix(), number, match[1]))

    return found


def listed_ids() -> set[str]:
    """The IDs in the first column of the open items table."""
    ids = set()

    for line in (ROOT / "docs/temp/open.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("|"):
            ids |= set(re.findall(ID, line.split("|")[1]))

    return ids


def test_every_open_marker_names_an_id():
    found = markers()
    assert found, "no # OPEN marker found: is the search looking in the right place?"
    bare = [f"{f}:{n}" for f, n, text in found if not LEADING_IDS.match(text)]

    assert not bare, f"# OPEN without an ID (write `# OPEN <ID>: question`): {bare}"


def test_every_marker_id_is_in_the_open_list():
    listed = listed_ids()
    missing = {}

    for file, number, text in markers():
        if match := LEADING_IDS.match(text):
            for found in re.findall(ID, match[1]):
                if found not in listed:
                    missing.setdefault(found, []).append(f"{file}:{number}")

    assert not missing, f"IDs missing from docs/temp/open.md: {missing}"
