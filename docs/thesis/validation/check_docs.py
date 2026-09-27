"""Consistency checks and generated views for the validation docs.

The issue register in issues.md is the single source for every issue. This
script checks that everything else agrees with it, keeps the numbering of the
code markers current, and rebuilds the tables and diagrams that are derived
from it (the blocks between
``<!-- BEGIN generated:NAME -->`` and ``<!-- END generated:NAME -->``).

    python docs/thesis/validation/check_docs.py          # check only
    python docs/thesis/validation/check_docs.py --write  # refresh, then check

Exit code 1 means an error (broken link, unknown ID, stale block, marker that
disagrees with the register). Warnings do not fail the run.
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SRC = REPO / "src_thesis"
ISSUES = HERE / "issues.md"
PLAN = HERE / "plan.md"
METHOD = HERE / "methodology.md"
README = HERE / "README.md"
AUDIT = HERE / "marlem-keep-replace-audit.md"
DOCS = [README, ISSUES, PLAN, METHOD, AUDIT]

TAG = {"❌": "FAULT", "⚠️": "DEVIATION", "❓": "DECIDE"}
ORIGINS = {"Paper", "Fidelity", "Code"}
STATUSES = ["open", "agreed", "fixed", "decided", "wontfix"]
CLOSED = {"fixed", "decided", "wontfix"}

# [P1] Fig. 2 level of every class the register may name ("—" = not in Fig. 2).
LEVEL = {
    "LocalEnergyMarket": "0",
    "ActionHandler": "0",
    "ObservationHandler": "0",
    "RewardHandler": "0",
    "OrderMatcher": "0",
    "SellerPricing": "0",
    "BidAskSpreadPricing": "0",
    "OtherPricing": "0",
    "Order": "0",
    "Trade": "0",
    "DSOAgent": "0",
    "ReputationHandler": "0",
    "TransactionBlock": "0",
    "Validator": "0",
    "GridNetwork": "0",
    "GridConfig": "0",
    "Location": "0",
    "ImplicitCooperation": "2",
    "MetricsHandlers": "2",
    "Plotter": "2",
    "DERAgent": "1",
    "Battery": "1",
    "CTDEModule": "1",
    "CTCEModule": "1",
    "RLTrainer": "1",
    "GroupedLEM": "1",
    "RLInference": "1",
    "ProfileHandler": "—",
    "DERProfileHandler": "—",
    "EnvConfigHandler": "—",
    "tests": "—",
    "CaseNotebooks": "—",
    "Docs": "—",
}
UNAUDITED = {"Plotter"}
LEVEL_TITLE = {
    "0": "Level 0: Platform Marketplace",
    "2": "Level 2: Implicit Cooperation",
    "1": "Level 1: MARL Agents",
    "—": "Outside Fig. 2: inputs, persistence, tests, notebooks",
}
# Call structure drawn inside each level diagram (caller --> callee).
EDGES = {
    "0": [
        ("LocalEnergyMarket", "ActionHandler"),
        ("LocalEnergyMarket", "OrderMatcher"),
        ("LocalEnergyMarket", "ReputationHandler"),
        ("LocalEnergyMarket", "RewardHandler"),
        ("LocalEnergyMarket", "ObservationHandler"),
        ("OrderMatcher", "Order"),
        ("OrderMatcher", "Trade"),
        ("OrderMatcher", "SellerPricing"),
        ("OrderMatcher", "BidAskSpreadPricing"),
        ("OrderMatcher", "OtherPricing"),
        ("OrderMatcher", "DSOAgent"),
        ("OrderMatcher", "GridNetwork"),
        ("OrderMatcher", "Validator"),
        ("Validator", "TransactionBlock"),
        ("GridNetwork", "GridConfig"),
        ("GridNetwork", "Location"),
    ],
    "2": [
        ("ImplicitCooperation", "MetricsHandlers"),
        ("ImplicitCooperation", "Plotter"),
    ],
    "1": [
        ("DERAgent", "Battery"),
        ("RLTrainer", "GroupedLEM"),
        ("RLTrainer", "CTDEModule"),
        ("RLTrainer", "CTCEModule"),
        ("RLInference", "CTDEModule"),
    ],
    "—": [("DERProfileHandler", "ProfileHandler")],
}
STAGES = {
    "A": "A: Level 0, Platform Marketplace",
    "B": "B: Level 2, Implicit Cooperation",
    "C": "C: Level 0 agent interface",
    "D": "D: Level 1, MARL Agents",
}

errors: list[str] = []
warnings: list[str] = []


# --------------------------------------------------------------------------- parsing
PIPE = re.compile(r"(?<!\\)\|")
ROW = re.compile(r'^\| <a id="I-(\d{2})"></a>I-\d{2} \|')
BLOCK = re.compile(
    r"(<!-- BEGIN generated:([\w-]+) -->\n)(.*?)(<!-- END generated:\2 -->)", re.S
)


def cells(line: str) -> list[str]:
    return [c.strip() for c in PIPE.split(line.strip().strip("|"))]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def parse_register() -> dict[int, dict]:
    reg: dict[int, dict] = {}
    for n, line in enumerate(read(ISSUES).splitlines(), 1):
        m = ROW.match(line)
        if not m:
            continue
        c = cells(line)
        if len(c) != 11:
            errors.append(
                f"issues.md:{n}: register row has {len(c)} columns, expected 11"
            )
            continue
        iid = int(m.group(1))
        if iid in reg:
            errors.append(f"issues.md:{n}: duplicate I-{iid:02d}")
        reg[iid] = dict(
            id=iid,
            classes=[x.strip() for x in c[1].split(",")],
            step=c[2],
            origin=c[3],
            type=c[4],
            status=c[5],
            text=c[6].replace("\\|", "|"),
            code=c[7],
            ev=c[8],
            method=c[9],
            old=c[10],
            line=n,
        )
    if list(reg) != sorted(reg):
        errors.append("issues.md: register rows are not in ID order")
    return reg


def plan_steps() -> list[str]:
    return re.findall(r"^### ([A-D]\d+)\. ", read(PLAN), re.M)


# A sentence ends at ". " unless the word before the dot is an abbreviation.
SENTENCE_END = re.compile(r"(?<!\beq)(?<!\bAlg)(?<!\be\.g)(?<!\bi\.e)(?<!\bvs)\.\s")


def first_sentence(text: str) -> str:
    """The first sentence of a register text, without links ("eq. 20" is kept)."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text).strip()
    m = SENTENCE_END.search(text)
    return (text[: m.start()] if m else text).rstrip(".")


def short(text: str, n: int = 110) -> str:
    text = first_sentence(text)
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + " …"


def link(iid: int) -> str:
    return f"[I-{iid:02d}](issues.md#I-{iid:02d})"


# --------------------------------------------------------------------------- checks
def check_register(reg: dict[int, dict]) -> None:
    steps = set(plan_steps())
    for r in reg.values():
        where = f"issues.md:{r['line']} I-{r['id']:02d}"
        for cls in r["classes"]:
            if cls not in LEVEL:
                errors.append(
                    f"{where}: unknown class {cls!r} (add it to LEVEL in check_docs.py)"
                )
        if r["step"] not in steps:
            errors.append(f"{where}: step {r['step']!r} has no heading in plan.md")
        if r["origin"] not in ORIGINS:
            errors.append(f"{where}: origin {r['origin']!r}")
        if r["type"] not in TAG:
            errors.append(f"{where}: type {r['type']!r}")
        if r["status"] not in STATUSES:
            errors.append(f"{where}: status {r['status']!r}")


def check_ids(reg: dict[int, dict]) -> None:
    for doc in DOCS:
        for n, line in enumerate(read(doc).splitlines(), 1):
            for m in re.finditer(r"\bI-(\d{2})\b", line):
                if int(m.group(1)) not in reg:
                    errors.append(f"{doc.name}:{n}: unknown issue I-{m.group(1)}")


def slug(heading: str) -> str:
    s = heading.strip().lower()
    s = re.sub(r"[^\w\- ]", "", s, flags=re.U)
    return s.replace(" ", "-")


def anchors(path: Path) -> set[str]:
    t = read(path)
    found = {slug(h) for h in re.findall(r"^#{1,6} (.+)$", t, re.M)}
    found |= set(re.findall(r'<a id="([^"]+)"></a>', t))
    return found


def check_links() -> None:
    cache: dict[Path, set[str]] = {}
    for doc in DOCS:
        for n, line in enumerate(read(doc).splitlines(), 1):
            for m in re.finditer(r"\]\((<[^>]+>|[^)\s]+)\)", line):
                target = m.group(1).strip("<>")
                if re.match(r"[a-z]+:", target):
                    continue
                path_part, _, frag = target.partition("#")
                path = (doc.parent / path_part).resolve() if path_part else doc
                if not path.exists():
                    errors.append(f"{doc.name}:{n}: broken link {target}")
                    continue
                if not frag:
                    continue
                lm = re.fullmatch(r"L(\d+)(?:-L(\d+))?", frag)
                if lm:
                    size = len(
                        path.read_text(encoding="utf-8", errors="replace").splitlines()
                    )
                    last = int(lm.group(2) or lm.group(1))
                    if last > size:
                        errors.append(
                            f"{doc.name}:{n}: {target} is past the end of the file "
                            f"({size} lines)"
                        )
                elif path.suffix == ".md":
                    if path not in cache:
                        cache[path] = anchors(path)
                    if frag not in cache[path]:
                        errors.append(
                            f"{doc.name}:{n}: missing anchor #{frag} in {path.name}"
                        )


MARKER = re.compile(r"#\s*(FAULT|DEVIATION|DECIDE) I-(\d{2}) \[([A-D]\d+)\]")


NUMBERED = re.compile(
    r"^(?P<indent>\s*)# (?P<tag>FAULT|DEVIATION|DECIDE) (?P<id>I-\d{2}) "
    r"\[(?P<step>[A-D]\d+)\] (?:\(\d+/\d+; (?:next|first) [^)]*\) )?(?P<text>.*)$"
)


def number_markers(write: bool) -> None:
    """Keep ``(k/n; next <path>:<line>)`` on markers of multi-location issues current.

    Markers of one issue are ordered by file path, then line; the last one points
    back to the first. Only comment text changes, so line numbers stay the same.
    """
    files: dict[Path, list[str]] = {}
    found: dict[str, list[tuple[Path, int]]] = defaultdict(list)
    for py in sorted(SRC.rglob("*.py")):
        lines = py.read_text(encoding="utf-8").split("\n")
        files[py] = lines
        for n, line in enumerate(lines, 1):
            m = NUMBERED.match(line)
            if m:
                found[m.group("id")].append((py, n))
    stale: set[Path] = set()
    for issue, locs in found.items():
        locs.sort(key=lambda loc: (loc[0].relative_to(SRC).as_posix(), loc[1]))
        for k, (py, n) in enumerate(locs):
            m = NUMBERED.match(files[py][n - 1])
            head = f"{m.group('indent')}# {m.group('tag')} {issue} [{m.group('step')}]"
            if len(locs) == 1:
                new = f"{head} {m.group('text')}"
            else:
                last = k + 1 == len(locs)
                target, word = (locs[0], "first") if last else (locs[k + 1], "next")
                ref = f"{target[0].relative_to(SRC).as_posix()}:{target[1]}"
                new = f"{head} ({k + 1}/{len(locs)}; {word} {ref}) {m.group('text')}"
            if new != files[py][n - 1]:
                files[py][n - 1] = new
                stale.add(py)
    for py in sorted(stale):
        rel = py.relative_to(REPO).as_posix()
        if write:
            py.write_text("\n".join(files[py]), encoding="utf-8", newline="\n")
            print(f"renumbered markers in {rel}")
        else:
            errors.append(f"{rel}: marker numbering is stale; run with --write")


def check_markers(reg: dict[int, dict]) -> None:
    seen: dict[int, list[str]] = defaultdict(list)
    for py in sorted(SRC.rglob("*.py")):
        rel = py.relative_to(REPO).as_posix()
        for n, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            m = MARKER.search(line)
            if not m:
                continue
            tag, iid, step = m.group(1), int(m.group(2)), m.group(3)
            where = f"{rel}:{n}"
            seen[iid].append(where)
            r = reg.get(iid)
            if r is None:
                errors.append(f"{where}: marker for unknown I-{iid:02d}")
                continue
            if r["status"] in CLOSED:
                errors.append(
                    f"{where}: I-{iid:02d} is {r['status']}; delete its marker"
                )
            if TAG.get(r["type"]) != tag:
                errors.append(
                    f"{where}: marker says {tag}, register type is {r['type']}"
                )
            if r["step"] != step:
                errors.append(
                    f"{where}: marker says [{step}], register step is {r['step']}"
                )
    for r in reg.values():
        if (
            r["status"] not in CLOSED
            and r["id"] not in seen
            and "src_thesis/" in r["code"]
        ):
            code = short(r["code"], 60)
            warnings.append(f"I-{r['id']:02d}: no marker in src_thesis/ (code: {code})")


# ---------------------------------------------------------------------- generated views
def counts(rows) -> Counter:
    return Counter(r["type"] for r in rows)


def worst(c: Counter) -> str:
    for t, cls in (("❌", "bad"), ("⚠️", "warn"), ("❓", "open")):
        if c[t]:
            return cls
    return "ok"


def node_label(name: str, c: Counter) -> str:
    if name in UNAUDITED and not sum(c.values()):
        return f"{name}<br/>not audited"
    return f"{name}<br/>❌ {c['❌']} · ⚠️ {c['⚠️']} · ❓ {c['❓']}"


CLASSDEFS = [
    "  classDef bad fill:#fecaca,stroke:#b91c1c,color:#111",
    "  classDef warn fill:#fef3c7,stroke:#b45309,color:#111",
    "  classDef open fill:#e5e7eb,stroke:#4b5563,color:#111",
    "  classDef ok fill:#dcfce7,stroke:#15803d,color:#111",
]


def gen_fault_map(reg: dict[int, dict]) -> str:
    live = [r for r in reg.values() if r["status"] not in CLOSED]
    per_class: dict[str, list] = defaultdict(list)
    per_level: dict[str, list] = defaultdict(list)
    for r in live:
        for cls in r["classes"]:
            per_class[cls].append(r)
        for lvl in {LEVEL.get(c, "—") for c in r["classes"]}:
            per_level[lvl].append(r)
    out = [
        "Colour = the worst **open** issue in the box: red ❌, amber ⚠️, grey ❓ (or "
        "not audited), green none.",
        "An issue that touches several classes is counted in each.",
        "",
        "```mermaid",
        "flowchart LR",
    ]
    ids = {"0": "V0", "2": "V2", "1": "V1", "—": "Vx"}
    for lvl in ["0", "2", "1", "—"]:
        c = counts(per_level[lvl])
        title = LEVEL_TITLE[lvl].replace(": ", "<br/>")
        label = f"{title}<br/>❌ {c['❌']} · ⚠️ {c['⚠️']} · ❓ {c['❓']}"
        out.append(f'  {ids[lvl]}["{label}"]:::{worst(c)}')
    out += [
        "  Vx -->|inputs| V0",
        "  V0 -->|trades, settlement| V2",
        "  V2 -->|KPIs to reward and observation| V0",
        "  V0 -->|observation, reward| V1",
        "  V1 -->|actions| V0",
        *CLASSDEFS,
        "```",
    ]
    for lvl in ["0", "2", "1", "—"]:
        names = [c for c, v in LEVEL.items() if v == lvl]
        out += ["", f"**{LEVEL_TITLE[lvl]}**", "", "```mermaid", "flowchart LR"]
        groups: dict[str, list[str]] = defaultdict(list)
        for i, name in enumerate(names):
            c = counts(per_class[name])
            out.append(f'  C{i}["{node_label(name, c)}"]')
            groups[
                "open" if name in UNAUDITED and not sum(c.values()) else worst(c)
            ].append(f"C{i}")
        for a, b in EDGES[lvl]:
            out.append(f"  C{names.index(a)} --> C{names.index(b)}")
        out += CLASSDEFS
        out += [f"  class {','.join(v)} {k}" for k, v in groups.items()]
        out.append("```")
    return "\n".join(out) + "\n"


def gen_step(reg: dict[int, dict], step: str) -> str:
    rows = [r for r in reg.values() if r["step"] == step]
    if not rows:
        return "No issues.\n"
    out = ["| ID | Type | Origin | Status | Issue |", "|---|---|---|---|---|"]
    for r in rows:
        text = first_sentence(r["text"]).replace("|", "\\|")
        out.append(
            f"| {link(r['id'])} | {r['type']} | {r['origin']} | {r['status']} | "
            f"{text} |"
        )
    return "\n".join(out) + "\n"


def gen_progress(reg: dict[int, dict]) -> str:
    out = [
        "| Stage | Issues | " + " | ".join(STATUSES) + " |",
        "|---|---|" + "---|" * len(STATUSES),
    ]
    total = Counter()
    for key, title in STAGES.items():
        rows = [r for r in reg.values() if r["step"].startswith(key)]
        c = Counter(r["status"] for r in rows)
        total.update(c)
        out.append(
            f"| {title} | {len(rows)} | "
            + " | ".join(str(c[s]) for s in STATUSES)
            + " |"
        )
    out.append(
        f"| **Total** | **{sum(total.values())}** | "
        + " | ".join(f"**{total[s]}**" for s in STATUSES)
        + " |"
    )
    return "\n".join(out) + "\n"


def gen_register_totals(reg: dict[int, dict]) -> str:
    out = ["| Origin | ❌ | ⚠️ | ❓ | Total |", "|---|---|---|---|---|"]
    for origin in ["Paper", "Fidelity", "Code"]:
        c = counts(r for r in reg.values() if r["origin"] == origin)
        out.append(
            f"| {origin} | {c['❌']} | {c['⚠️']} | {c['❓']} | {sum(c.values())} |"
        )
    c = counts(reg.values())
    out.append(
        f"| **Total** | **{c['❌']}** | **{c['⚠️']}** | **{c['❓']}** | "
        f"**{sum(c.values())}** |"
    )
    return "\n".join(out) + "\n"


def gen_old_ids(reg: dict[int, dict]) -> str:
    back: dict[str, list[int]] = defaultdict(list)
    for r in reg.values():
        for old in re.findall(r"P\d-\d{2}", r["old"]):
            back[old].append(r["id"])
    out = ["| Old ID | Issues |", "|---|---|"]
    for old in sorted(back, key=lambda s: (s[:2], int(s[3:]))):
        out.append(f"| {old} | " + ", ".join(link(i) for i in back[old]) + " |")
    return "\n".join(out) + "\n"


def gen_method_status() -> str:
    t = read(METHOD)
    parts = re.split(
        r"^### Implementation in the original code \((§\d+)[^)]*\)\s*$", t, flags=re.M
    )
    out = ["| Section | ✅ | ⚠️ | ❌ | ❓ |", "|---|---|---|---|---|"]
    total = Counter()
    for sec, body in zip(parts[1::2], parts[2::2]):
        table = re.match(r"\s*((?:\|.*\n)+)", body)
        c = Counter()
        for line in (table.group(1).splitlines()[2:] if table else []):
            status = cells(line)[2]
            for mark in ("✅", "⚠️", "❌", "❓"):
                if mark in status:
                    c[mark] += 1
                    break
        total.update(c)
        out.append(f"| {sec} | {c['✅']} | {c['⚠️']} | {c['❌']} | {c['❓']} |")
    out.append(
        f"| **Total** | **{total['✅']}** | **{total['⚠️']}** | **{total['❌']}** | "
        f"**{total['❓']}** |"
    )
    return "\n".join(out) + "\n"


def generators(reg: dict[int, dict]) -> dict[Path, dict[str, str]]:
    plan = {"fault-map": gen_fault_map(reg), "progress": gen_progress(reg)}
    for step in plan_steps():
        plan[f"step-{step}"] = gen_step(reg, step)
    return {
        PLAN: plan,
        ISSUES: {
            "register-totals": gen_register_totals(reg),
            "old-ids": gen_old_ids(reg),
        },
        METHOD: {"method-status": gen_method_status()},
    }


def refresh(write: bool, reg: dict[int, dict]) -> None:
    for path, blocks in generators(reg).items():
        text = read(path)
        found = {m.group(2) for m in BLOCK.finditer(text)}
        for name in blocks.keys() - found:
            errors.append(f"{path.name}: missing generated block {name!r}")

        def sub(m: re.Match) -> str:
            new = blocks.get(m.group(2))
            if new is None:
                errors.append(f"{path.name}: unknown generated block {m.group(2)!r}")
                return m.group(0)
            return m.group(1) + new + m.group(4)

        new_text = BLOCK.sub(sub, text)
        if new_text != text:
            if write:
                path.write_text(new_text, encoding="utf-8", newline="\n")
                print(f"updated {path.name}")
            else:
                errors.append(
                    f"{path.name}: generated blocks are stale; run with --write"
                )


def main() -> int:
    write = "--write" in sys.argv
    reg = parse_register()
    check_register(reg)
    refresh(write, reg)
    number_markers(write)
    check_ids(reg)
    check_links()
    check_markers(reg)
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    live = sum(r["status"] not in CLOSED for r in reg.values())
    print(
        f"{len(reg)} issues ({live} not closed); {len(errors)} errors, "
        f"{len(warnings)} warnings"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
