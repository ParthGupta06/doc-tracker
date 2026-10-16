"""System service: pod project API plus the course testing endpoints."""

from __future__ import annotations

import logging
import threading
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from doctracker import __version__, coverage_tracker
from doctracker.system.analysis import run_analysis
from doctracker.system.classify import load_config
from doctracker.system.gitops import CommitNotFound, GitFailure, RepositoryNotFound
from doctracker.system.models import AnalysisRequest, AnalysisResult, ErrorBody, TestSetupRequest
from doctracker.system.storage import ANALYSIS_ID, StorageError, build_store

log = logging.getLogger("doctracker.system")

app = FastAPI(title="Documentation Tracker System", version=__version__,
              description="Teams 15/16 pod project API (Phase 2, Section 5) and course testing endpoints.")
store = build_store()
sessions: dict[str, dict[str, Any]] = {}
sessions_lock = threading.Lock()

TEST_PATHS = ("/test/setup", "/test/report")


def project_error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code, "message": message})


def test_error(status: int, message: str, source: str = "system") -> JSONResponse:
    return JSONResponse(status_code=status, content={"message": message, "source": source})


def describe(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "invalid request"
    first = errors[0]
    loc = [str(p) for p in first.get("loc", ()) if p != "body"]
    field = ".".join(loc)
    kind = first.get("type", "")
    if kind == "json_invalid":
        return "request body is not valid JSON"
    if kind == "missing":
        return f"{field} is required"
    if kind == "string_pattern_mismatch" and field == "repository":
        return "repository must use the format owner/name"
    if kind == "string_pattern_mismatch":
        return f"{field} must be a 7-40 character hexadecimal commit SHA"
    if kind in ("string_type", "dict_type", "model_attributes_type"):
        return f"{field or 'body'} has the wrong type"
    return f"{field or 'body'}: {first.get('msg', 'invalid value')}"


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    message = describe(exc)
    log.info("request rejected", extra={"path": request.url.path, "reason": message})
    if request.url.path.endswith(TEST_PATHS):
        return test_error(400, message)
    return project_error(400, "INVALID_REQUEST", message)


@app.get("/health", tags=["operations"])
def health() -> dict[str, Any]:
    return {"status": "ok", "tool_version": __version__, "config_version": load_config().config_version,
            "storage": store.backend}


@app.post("/analyze", response_model=AnalysisResult, tags=["project"],
          responses={400: {"model": ErrorBody}, 404: {"model": ErrorBody}, 500: {"model": ErrorBody}})
def analyze(req: AnalysisRequest) -> Any:
    try:
        return run_analysis(req, store)
    except RepositoryNotFound:
        return project_error(404, "REPOSITORY_NOT_FOUND", f"repository {req.repository} was not found or is not public")
    except CommitNotFound as exc:
        return project_error(404, "COMMIT_NOT_FOUND", f"commit {exc} was not found in {req.repository}")
    except StorageError as exc:
        log.error("evidence write failed", extra={"reason": str(exc)})
        return project_error(500, "STORAGE_FAILED", "analysis evidence could not be saved; no result was recorded")
    except GitFailure as exc:
        log.error("analysis failed", extra={"reason": str(exc)})
        return project_error(500, "ANALYSIS_FAILED", "repository analysis failed")
    except Exception:
        log.exception("unexpected analysis failure")
        return project_error(500, "ANALYSIS_FAILED", "unexpected internal error")


@app.get("/analysis/{analysis_id}", response_model=AnalysisResult, tags=["project"],
         responses={404: {"model": ErrorBody}, 500: {"model": ErrorBody}})
def get_analysis(analysis_id: str) -> Any:
    if not ANALYSIS_ID.match(analysis_id):
        return project_error(404, "ANALYSIS_NOT_FOUND", f"analysis {analysis_id} does not exist")
    try:
        result = store.load(analysis_id)
    except StorageError as exc:
        log.error("evidence read failed", extra={"analysis_id": analysis_id, "reason": str(exc)})
        return project_error(500, "STORAGE_FAILED", "saved analysis could not be retrieved")
    if result is None:
        return project_error(404, "ANALYSIS_NOT_FOUND", f"analysis {analysis_id} does not exist")
    return result


@app.post("/test/setup", status_code=201, tags=["testing"])
def test_setup(req: TestSetupRequest) -> Any:
    with sessions_lock:
        if req.session_id in sessions:
            return test_error(409, f"session {req.session_id} already exists")
        try:
            tracker = coverage_tracker.start()
            tracker.begin(req.session_id)
        except Exception:
            log.exception("session setup failed")
            return test_error(500, "could not initialize coverage measurement for the session")
        sessions[req.session_id] = {"setup": req.setup}
    log.info("test session ready", extra={"session_id": req.session_id})
    return {"session_id": req.session_id}


@app.get("/test/report", tags=["testing"])
def test_report(session_id: str | None = Query(default=None)) -> Any:
    if not session_id:
        return test_error(400, "session_id query parameter is required")
    if session_id not in sessions:
        return test_error(404, f"session {session_id} is unknown")
    return {"session_id": session_id, "coverage": {"code": coverage_tracker.start().report(session_id)}}
