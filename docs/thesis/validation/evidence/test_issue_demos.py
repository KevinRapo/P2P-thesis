"""One acceptance test per issue demo.

Each test asserts the behaviour the paper specifies. While the issue is present
the test fails and is reported as XFAIL. When a fix makes it pass, strict xfail
turns the XPASS into a failure: remove the xfail for that issue, set its status
in issues.md and delete its code marker in the same commit.

    python -m pytest docs/thesis/validation/evidence -q
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from issue_demos import REGISTRY, same, showability  # noqa: E402

# Issues whose demo is expected to pass: move an ID here when it is fixed.
FIXED: set[str] = set()


@pytest.mark.parametrize(
    "issue",
    [
        pytest.param(
            i,
            marks=(
                ()
                if i in FIXED
                else pytest.mark.xfail(strict=True, reason=f"{i}: {REGISTRY[i].title}")
            ),
        )
        for i in sorted(REGISTRY)
    ],
)
def test_issue(issue: str) -> None:
    d = REGISTRY[issue]()
    assert same(
        d.actual, d.expected
    ), f"{issue}: expected {d.expected!r} ({d.expected_label}), got {d.actual!r}"


def test_every_issue_has_a_showability_tier() -> None:
    tiers = showability()
    assert sorted(tiers) == [f"I-{n:02d}" for n in range(1, 81)]
    assert {t for t, _ in tiers.values()} <= {"demo", "inspect", "harness", "judgment"}
