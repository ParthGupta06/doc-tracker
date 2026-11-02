"""Analysis pipeline: resolve versions, diff, classify, persist (REQ-01, REQ-04, REQ-05)."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from doctracker import __version__
from doctracker.system.classify import load_config
from doctracker.system.detect import detect
from doctracker.system.gitops import Workspace
from doctracker.system.models import AnalysisRequest
from doctracker.system.storage import EvidenceStore

log = logging.getLogger("doctracker.analysis")


def new_analysis_id() -> str:
    return f"an-{uuid.uuid4().hex}"


def run_analysis(req: AnalysisRequest, store: EvidenceStore) -> dict[str, Any]:
    config = load_config()
    analysis_id = new_analysis_id()
    started = time.perf_counter()
    stage = "fetch"
    log.info("analysis started", extra={"analysis_id": analysis_id, "repository": req.repository,
                                         "commit_id": req.commit_id, "base_commit": req.base_commit})
    try:
        with Workspace(req.repository) as ws:
            ws.clone()
            stage = "resolve"
            head = ws.resolve(req.commit_id.lower())
            base = ws.resolve(req.base_commit.lower()) if req.base_commit else ws.first_parent(head)
            stage = "diff"
            raw = ws.diff(base, head)
            stage = "detect"
            issues, unmapped, mapping_error = (detect(ws, base, head, raw, config)
                                               if len(raw) <= config.max_changed_files else ([], [], None))
    except Exception:
        log.info("analysis stopped", extra={"analysis_id": analysis_id, "stage": stage,
                                            "duration_ms": round((time.perf_counter() - started) * 1000)})
        raise

    stage = "classify"
    status = "SUCCESS"
    error = None
    changes: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    if len(raw) > config.max_changed_files:
        status = "ERROR"
        error = {"code": "CHANGE_LIMIT_EXCEEDED",
                 "message": f"{len(raw)} changed files exceeds the limit of {config.max_changed_files}"}
    else:
        for rc in sorted(raw, key=lambda c: (c.path, c.old_path or "")):
            changes.append({"path": rc.path, "old_path": rc.old_path, "change_type": rc.change_type,
                            "category": config.classify(rc.path)})
            if not config.is_supported(rc.path):
                skipped.append({"path": rc.path, "reason": "UNSUPPORTED_FILE_TYPE"})
    if mapping_error:
        status = "ERROR"
        error = mapping_error
    result: dict[str, Any] = {
        "analysis_id": analysis_id,
        "repository": req.repository,
        "head_commit": head,
        "base_commit": base,
        "config_version": config.config_version,
        "tool_version": __version__,
        "status": status,
        "error": error,
        "issues": issues,
        "changes": changes,
        "skipped": skipped,
        "unmapped": unmapped,
        "created_at": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    }
    stage = "persist"
    store.save(analysis_id, result)
    log.info("analysis completed", extra={
        "analysis_id": analysis_id, "status": status, "changes": len(changes), "skipped": len(skipped), "findings": len(issues),
        "head_commit": head, "base_commit": base, "config_version": config.config_version,
        "storage": store.backend, "duration_ms": round((time.perf_counter() - started) * 1000)})
    return result
