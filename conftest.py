"""Repository-wide pytest configuration.

The failure report below exists because the CI job logs are not always reachable
from outside the runner. GitHub Actions turns any ``::error::`` line in a step's
output into a check-run annotation, and annotations can be read through the API,
so a failing test reports its own message there as well as in the log.
"""

from __future__ import annotations

import os


def pytest_runtest_logreport(report) -> None:
    if not report.failed:
        return
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    text = str(report.longrepr)
    # Keep each annotation short: the API caps what it will return, and the head
    # of a traceback (the assertion and the values) is the useful part.
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    # The assertion message sits at the end of a traceback, so the tail matters
    # as much as the head. Report both, labelled, inside the annotation budget.
    tail = lines[-25:]
    for line in tail:
        print(f"::error title=pytest-tail {report.nodeid}::{line[:900]}")
    for line in lines[:15]:
        print(f"::error title=pytest {report.nodeid}::{line[:900]}")
    print(f"::error title=pytest {report.nodeid}::total failure lines {len(lines)}")
