"""Request-scoped line coverage: a worker retains its session through cancellation/rollover."""
from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from types import FrameType
from typing import Any

import coverage

MEASURED_DIR = Path(__file__).resolve().parent / 'system'


class RequestContext(coverage.CoveragePlugin):
    def dynamic_context(self, frame: FrameType) -> str | None:
        if frame.f_code is call.__code__:
            return str(frame.f_locals['session_id']) or 'unassigned'
        return None


def register(plugins: Any) -> None:
    plugins.add_dynamic_context(RequestContext())


def call[**P, T](session_id: str, fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """Coverage's dynamic context covers this frame and descendants in this thread."""
    return fn(*args, **kwargs)


class SessionCoverage:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.cov: coverage.Coverage | None = None
        self.error: str | None = None
        try:
            if coverage.Coverage.current() is not None:
                # Do not corrupt an enclosing CI coverage collection or attribute its global context to sessions.
                self.error = 'external coverage collector active; session-specific measurement unavailable'
            else:
                self.cov = coverage.Coverage(source_pkgs=['doctracker.system'], data_file=None, plugins=[register])
                self.cov.set_option('run:core', 'ctrace')
                self.cov.start()
        except Exception as exc:  # pragma: no cover - platform-specific
            self.cov = None
            self.error = type(exc).__name__

    def begin(self, session_id: str) -> None:
        # Context is captured by each request, never switched globally at setup.
        pass

    def report(self, session_id: str) -> dict[str, Any]:
        if self.cov is None:
            return {'covered': None, 'total': None, 'basis': 'Source lines unavailable: ' + str(self.error)}
        with self.lock:
            data = self.cov.get_data()
            covered = total = 0
            for filename in sorted(MEASURED_DIR.glob('*.py')):
                path = str(filename)
                _, statements, _, _, _ = self.cov.analysis2(path)
                statement_set = set(statements)
                total += len(statement_set)
                covered += sum(1 for line, contexts in data.contexts_by_lineno(path).items()
                               if line in statement_set and session_id in contexts)
        return {'covered': covered, 'total': total,
                'basis': 'Executable doctracker.system lines in request-scoped coverage.py contexts; '
                         'each request retains the session captured at entry'}


tracker: SessionCoverage | None = None


def start() -> SessionCoverage:
    global tracker
    if tracker is None:
        tracker = SessionCoverage()
    return tracker
