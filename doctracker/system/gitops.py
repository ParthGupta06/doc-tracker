"""Read-only access to public GitHub repositories through the git CLI (REQ-01, REQ-06).

Repository content is untrusted: clones are bare (no checkout), hooks are
disabled, external diff and textconv drivers are never invoked, and no file
from the repository is executed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
GIT_TIMEOUT_SECONDS = 60

STATUS_NAMES = {
    "A": "ADDED",
    "M": "MODIFIED",
    "D": "DELETED",
    "R": "RENAMED",
    "C": "COPIED",
    "T": "TYPE_CHANGED",
}


class RepositoryNotFound(Exception):
    pass


class CommitNotFound(Exception):
    pass


class GitFailure(Exception):
    pass


@dataclass(frozen=True)
class RawChange:
    path: str
    change_type: str
    old_path: str | None


def _env(home: str) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": home,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/bin/false",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "LC_ALL": "C",
    }
    for key in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy",
                "GIT_SSL_CAINFO", "SSL_CERT_FILE"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


GIT_BASE = os.environ.get("DOCTRACKER_GIT_BASE", "https://github.com").rstrip("/")
ALLOWED_PROTOCOL = "file" if GIT_BASE.startswith("file://") else "https"

SAFE_FLAGS = ["-c", "core.hooksPath=/dev/null", "-c", "protocol.allow=never",
              "-c", f"protocol.{ALLOWED_PROTOCOL}.allow=always", "-c", "diff.external="]


class Workspace:
    """A temporary bare clone that is deleted when the analysis finishes."""

    def __init__(self, repository: str):
        self.repository = repository
        self.root = tempfile.mkdtemp(prefix="doctracker-")
        self.git_dir = os.path.join(self.root, "repo.git")
        self.env = _env(self.root)

    def __enter__(self) -> Workspace:
        return self

    def __exit__(self, *exc: object) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        try:
            proc = subprocess.run(
                ["git", *SAFE_FLAGS, "--git-dir", self.git_dir, *args],
                env=self.env, capture_output=True, text=True, timeout=GIT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitFailure(f"git {args[0]} timed out after {GIT_TIMEOUT_SECONDS}s") from exc
        if check and proc.returncode != 0:
            raise GitFailure(f"git {args[0]} failed: {proc.stderr.strip()[:300]}")
        return proc

    def clone(self) -> None:
        url = f"{GIT_BASE}/{self.repository}.git"
        try:
            proc = subprocess.run(
                ["git", *SAFE_FLAGS, "clone", "--bare", "--quiet", "--filter=blob:none", url, self.git_dir],
                env=self.env, capture_output=True, text=True, timeout=GIT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitFailure(f"clone timed out after {GIT_TIMEOUT_SECONDS}s") from exc
        if proc.returncode != 0:
            err = proc.stderr.lower()
            if ("not found" in err or "does not appear to be a git repository" in err or "could not read username" in err
                    or "authentication failed" in err or "terminal prompts disabled" in err):
                raise RepositoryNotFound(self.repository)
            raise GitFailure(f"clone failed: {proc.stderr.strip()[:300]}")

    def resolve(self, commit: str) -> str:
        proc = self._git("rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}", check=False)
        if proc.returncode != 0 and len(commit) == 40:
            self._git("fetch", "--quiet", "--filter=blob:none", "origin", commit, check=False)
            proc = self._git("rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}", check=False)
        if proc.returncode != 0:
            raise CommitNotFound(commit)
        return proc.stdout.strip()

    def first_parent(self, commit: str) -> str | None:
        proc = self._git("rev-parse", "--verify", "--quiet", f"{commit}^1", check=False)
        return proc.stdout.strip() if proc.returncode == 0 else None

    def diff(self, base: str | None, head: str) -> list[RawChange]:
        out = self._git(
            "diff-tree", "-r", "-z", "-M", "--no-ext-diff", "--no-textconv", "--name-status",
            base or EMPTY_TREE, head,
        ).stdout
        tokens = out.split("\0")
        changes: list[RawChange] = []
        i = 0
        while i < len(tokens) and tokens[i]:
            status = tokens[i]
            code = status[0]
            if code in ("R", "C"):
                changes.append(RawChange(path=tokens[i + 2], change_type=STATUS_NAMES[code], old_path=tokens[i + 1]))
                i += 3
            else:
                changes.append(RawChange(path=tokens[i + 1], change_type=STATUS_NAMES.get(code, "MODIFIED"), old_path=None))
                i += 2
        return changes
