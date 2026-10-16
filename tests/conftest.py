"""Builds the deterministic fixture repo locally and serves it through file:// for offline tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GIT_BASE = Path(os.environ.get("TEST_GIT_BASE", "/tmp/doctracker-test-gitbase"))

os.environ.setdefault("DOCTRACKER_GIT_BASE", f"file://{GIT_BASE}")
os.environ.setdefault("FIXTURE_REPO", "pod/fixtures")
os.environ.setdefault("EVIDENCE_DIR", str(GIT_BASE / "runs"))


def pytest_sessionstart(session: pytest.Session) -> None:
    work = GIT_BASE / "work"
    bare = GIT_BASE / "pod" / "fixtures.git"
    subprocess.run([sys.executable, str(ROOT / "fixtures" / "build_fixture_repo.py"), str(work)],
                   check=True, capture_output=True)
    if bare.exists():
        subprocess.run(["rm", "-rf", str(bare)], check=True)
    bare.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(bare)], check=True)
