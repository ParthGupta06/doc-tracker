"""Per-session line coverage of the system package (testing interface: GET /test/report).

coverage.py measures doctracker.system for the whole process. Each
POST /test/setup switches the dynamic context to the new session ID, so lines
executed by later project requests are attributed to that session. Only one
session is the measurement target at a time: a newer setup closes the
previous session's window, whose report stays readable but no longer grows.
"""

from __future__ import annotations

import os
import threading
from typing import Any

import coverage

MEASURED_PACKAGE = "doctracker.system"
MEASURED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "system") + os.sep


class SessionCoverage:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.cov: coverage.Coverage | None = None
        self.error: str | None = None
        try:
            existing = coverage.Coverage.current()
            if existing is not None:
                self.cov = existing
            else:
                self.cov = coverage.Coverage(source_pkgs=[MEASURED_PACKAGE], data_file=None, branch=False)
                self.cov.start()
        except Exception as exc:  # pragma: no cover - environment specific
            self.cov = None
            self.error = f"{type(exc).__name__}: {exc}"

    def begin(self, session_id: str) -> None:
        if self.cov is not None:
            with self.lock:
                self.cov.switch_context(session_id)

    def report(self, session_id: str) -> dict[str, Any]:
        if self.cov is None:
            return {"covered": None, "total": None,
                    "basis": f"Source lines; target instrumentation unavailable ({self.error})"}
        with self.lock:
            data = self.cov.get_data()
            covered = 0
            total = 0
            for filename in sorted(f for f in data.measured_files() if os.path.abspath(f).startswith(MEASURED_DIR)):
                _, statements, _, _, _ = self.cov.analysis2(filename)
                stmt_set = set(statements)
                total += len(stmt_set)
                by_line = data.contexts_by_lineno(filename)
                covered += sum(1 for line, ctxs in by_line.items() if line in stmt_set and session_id in ctxs)
        return {"covered": covered, "total": total,
                "basis": ("Executable source lines of the doctracker.system package executed while handling "
                          "this session's requests since setup (coverage.py, line coverage)")}


tracker: SessionCoverage | None = None


def start() -> SessionCoverage:
    global tracker
    if tracker is None:
        tracker = SessionCoverage()
    return tracker
