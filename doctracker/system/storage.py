"""Immutable evidence storage: one JSON file per analysis (REQ-04).

Two backends share the same contract: a run file is written once, never
overwritten, and must be durable before the API reports success.
- LocalStore writes to EVIDENCE_DIR (default ./data/runs).
- GitHubStore writes runs/<analysis_id>.json to EVIDENCE_REPO through the
  GitHub contents API using EVIDENCE_TOKEN; it survives container restarts.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Protocol

import httpx

log = logging.getLogger("doctracker.storage")

ANALYSIS_ID = re.compile(r"^an-[0-9a-f]{32}$")


class StorageError(Exception):
    pass


class EvidenceStore(Protocol):
    backend: str

    def save(self, analysis_id: str, result: dict[str, Any]) -> None: ...

    def load(self, analysis_id: str) -> dict[str, Any] | None: ...


def _encode(result: dict[str, Any]) -> bytes:
    return (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8")


class LocalStore:
    backend = "local"

    def __init__(self, directory: str):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    def save(self, analysis_id: str, result: dict[str, Any]) -> None:
        path = self.dir / f"{analysis_id}.json"
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
            with os.fdopen(fd, "wb") as fh:
                fh.write(_encode(result))
                fh.flush()
                os.fsync(fh.fileno())
        except OSError as exc:
            raise StorageError(f"could not write evidence file: {exc.strerror}") from exc

    def load(self, analysis_id: str) -> dict[str, Any] | None:
        path = self.dir / f"{analysis_id}.json"
        if not path.exists():
            return None
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            return data
        except (OSError, ValueError) as exc:
            raise StorageError(f"could not read evidence file: {exc}") from exc


class GitHubStore:
    backend = "github"

    def __init__(self, repo: str, token: str, branch: str = "main"):
        self.repo = repo
        self.branch = branch
        self.client = httpx.Client(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=20,
        )
        self.cache = LocalStore(os.environ.get("EVIDENCE_CACHE_DIR", "data/cache"))

    def save(self, analysis_id: str, result: dict[str, Any]) -> None:
        body = {
            "message": f"evidence: {analysis_id}",
            "content": base64.b64encode(_encode(result)).decode("ascii"),
            "branch": self.branch,
        }
        try:
            resp = self.client.put(f"/repos/{self.repo}/contents/runs/{analysis_id}.json", json=body)
        except httpx.HTTPError as exc:
            raise StorageError(f"evidence repository unreachable: {type(exc).__name__}") from exc
        if resp.status_code != 201:
            raise StorageError(f"evidence repository rejected write: HTTP {resp.status_code}")
        try:
            self.cache.save(analysis_id, result)
        except StorageError:
            log.warning("cache write failed", extra={"analysis_id": analysis_id})

    def load(self, analysis_id: str) -> dict[str, Any] | None:
        cached = self.cache.load(analysis_id)
        if cached is not None:
            return cached
        try:
            resp = self.client.get(
                f"/repos/{self.repo}/contents/runs/{analysis_id}.json",
                params={"ref": self.branch},
                headers={"Accept": "application/vnd.github.raw+json"},
            )
        except httpx.HTTPError as exc:
            raise StorageError(f"evidence repository unreachable: {type(exc).__name__}") from exc
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise StorageError(f"evidence repository read failed: HTTP {resp.status_code}")
        data: dict[str, Any] = resp.json()
        return data


def build_store() -> EvidenceStore:
    repo = os.environ.get("EVIDENCE_REPO")
    token = os.environ.get("EVIDENCE_TOKEN")
    if repo and token:
        return GitHubStore(repo, token, os.environ.get("EVIDENCE_BRANCH", "main"))
    return LocalStore(os.environ.get("EVIDENCE_DIR", "data/runs"))
