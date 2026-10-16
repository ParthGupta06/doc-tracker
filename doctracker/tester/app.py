"""Tester service: /test/setup, /test/run, /test/report (course cross-team testing interface)."""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StrictStr

from doctracker import __version__
from doctracker.tester.suite import ACCEPTANCE_CRITERIA, COMPONENTS, TESTS, Ctx, Fail, SystemError_

log = logging.getLogger("doctracker.tester")

FIXTURE_REPO = os.environ.get("FIXTURE_REPO", "OWNER/doc-tracker-fixtures")
SETUP_TIMEOUT = float(os.environ.get("TESTER_SETUP_TIMEOUT", "90"))
CALL_TIMEOUT = float(os.environ.get("TESTER_CALL_TIMEOUT", "90"))

app = FastAPI(title="Documentation Tracker Tester", version=__version__,
              description="Team 16 automated suite for the Teams 15/16 pod project API.")

sessions: dict[str, dict[str, Any]] = {}
lock = asyncio.Lock()


class SetupBody(BaseModel):
    target_url: StrictStr


class RunBody(BaseModel):
    session_id: StrictStr


def err(status: int, message: str, source: str = "tester") -> JSONResponse:
    return JSONResponse(status_code=status, content={"message": message, "source": source})


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
    return err(400, f"invalid request: {field or 'body'} {first.get('msg', '')}".strip())


def valid_target(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return "target_url must be an absolute http(s) URL"
    if parts.query or parts.fragment or parts.username or parts.password:
        return "target_url must not contain a query, fragment or credentials"
    if parts.path.rstrip("/").endswith("/test"):
        return "target_url must be the system base URL without /test"
    return None


@app.get("/health", tags=["operations"])
def health() -> dict[str, Any]:
    return {"status": "ok", "tool_version": __version__, "fixture_repo": FIXTURE_REPO, "tests": len(TESTS)}


@app.post("/test/setup", status_code=201, tags=["testing"])
async def setup(body: SetupBody) -> Any:
    problem = valid_target(body.target_url)
    if problem:
        return err(400, problem)
    target = body.target_url.rstrip("/")
    session_id = str(uuid.uuid4())
    try:
        async with httpx.AsyncClient(timeout=SETUP_TIMEOUT) as client:
            resp = await client.post(f"{target}/test/setup", json={"session_id": session_id, "setup": {}})
    except httpx.HTTPError as exc:
        log.warning("system setup unreachable", extra={"target_url": target, "error": type(exc).__name__})
        return err(500, f"system setup could not be reached: {type(exc).__name__}", "communication")
    if resp.status_code != 201:
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        message = payload.get("message") if isinstance(payload, dict) else None
        source = payload.get("source") if isinstance(payload, dict) else None
        return err(resp.status_code, message or f"system setup returned HTTP {resp.status_code}", source or "system")
    try:
        returned = resp.json().get("session_id")
    except (ValueError, AttributeError):
        returned = None
    if returned != session_id:
        return err(500, "system setup did not return the supplied session_id", "system")
    sessions[session_id] = {"target_url": target, "state": "ready", "report": None}
    log.info("tester session ready", extra={"session_id": session_id, "target_url": target})
    return {"session_id": session_id}


def coverage_block(executed: list[Any], code: dict[str, Any] | None) -> dict[str, Any]:
    comps = sorted({c for t in executed for c in t.components})
    acs = sorted({a for t in executed for a in t.criteria})
    return {
        "code": code or {"covered": None, "total": None,
                         "basis": "Source lines; target instrumentation unavailable"},
        "component": {"covered": len(comps), "total": len(COMPONENTS),
                      "basis": "Components C1-C7 listed in the pod specification exercised by at least one "
                               "executed test: " + (", ".join(comps) or "none")},
        "system": {"covered": len(acs), "total": len(ACCEPTANCE_CRITERIA),
                   "basis": "Acceptance criteria AC-01 to AC-10 in the pod specification exercised by at least "
                            "one executed test: " + (", ".join(acs) or "none")},
    }


def valid_code_coverage(value: Any) -> bool:
    if not isinstance(value, dict) or not isinstance(value.get("basis"), str) or not value["basis"]:
        return False
    cov, tot = value.get("covered"), value.get("total")
    if cov is None and tot is None:
        return True
    return isinstance(cov, int) and isinstance(tot, int) and 0 <= cov <= tot


async def fetch_code_coverage(client: httpx.AsyncClient, target: str, session_id: str) -> dict[str, Any] | None:
    try:
        resp = await client.get(f"{target}/test/report", params={"session_id": session_id})
        code = resp.json().get("coverage", {}).get("code") if resp.status_code == 200 else None
    except (httpx.HTTPError, ValueError, AttributeError):
        code = None
    return code if valid_code_coverage(code) else None


@app.post("/test/run", tags=["testing"])
async def run(body: RunBody) -> Any:
    async with lock:
        session = sessions.get(body.session_id)
        if session is None:
            return err(404, f"session {body.session_id} is unknown")
        if session["state"] != "ready":
            return err(409, f"session {body.session_id} has already run or is running")
        session["state"] = "running"
    target = session["target_url"]
    results: list[dict[str, Any]] = []
    executed: list[Any] = []
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=CALL_TIMEOUT) as client:
            ctx = Ctx(client=client, target=target, fixture_repo=FIXTURE_REPO)
            for case in TESTS:
                if case.fn is None:
                    results.append({"test_id": case.test_id, "outcome": "skip",
                                    "message": f"{case.title}: {case.skip_reason}"})
                    continue
                executed.append(case)
                try:
                    message = await case.fn(ctx)
                    results.append({"test_id": case.test_id, "outcome": "pass", "message": f"{case.title}: {message}"})
                except Fail as exc:
                    results.append({"test_id": case.test_id, "outcome": "fail", "message": f"{case.title}: {exc}"})
                except SystemError_ as exc:
                    results.append({"test_id": case.test_id, "outcome": "error", "source": "system",
                                    "message": f"{case.title}: {exc}"})
                except httpx.TimeoutException:
                    results.append({"test_id": case.test_id, "outcome": "error", "source": "communication",
                                    "message": f"{case.title}: request timed out. No response was available to evaluate."})
                except httpx.HTTPError as exc:
                    results.append({"test_id": case.test_id, "outcome": "error", "source": "communication",
                                    "message": f"{case.title}: {type(exc).__name__} contacting the system."})
                log.info("test finished", extra={"session_id": body.session_id, "test_id": case.test_id,
                                                 "outcome": results[-1]["outcome"]})
            code = await fetch_code_coverage(client, target, body.session_id)
    except Exception as exc:
        log.exception("tester aborted", extra={"session_id": body.session_id})
        done = {r["test_id"] for r in results}
        aborted_id = next((t.test_id for t in TESTS if t.test_id not in done), None)
        for case in TESTS:
            if case.test_id in done:
                continue
            if case.test_id == aborted_id:
                results.append({"test_id": case.test_id, "outcome": "error", "source": "tester",
                                "message": f"{case.title}: tester aborted ({type(exc).__name__})."})
            else:
                results.append({"test_id": case.test_id, "outcome": "skip",
                                "message": f"{case.title}: not executed because the tester aborted."})
        session["report"] = {"session_id": body.session_id, "target_url": target, "results": results,
                             "coverage": coverage_block(executed, None)}
        session["state"] = "aborted"
        return err(500, "tester aborted; retrieve available results with GET /test/report")
    report = {"session_id": body.session_id, "target_url": target, "results": results,
              "coverage": coverage_block(executed, code)}
    session["report"] = report
    session["state"] = "done"
    counts = {o: sum(1 for r in results if r["outcome"] == o) for o in ("pass", "fail", "error", "skip")}
    log.info("suite finished", extra={"session_id": body.session_id, "target_url": target, **counts,
                                      "duration_ms": round((time.perf_counter() - started) * 1000)})
    return report


@app.get("/test/report", tags=["testing"])
def report(session_id: str | None = Query(default=None)) -> Any:
    if not session_id:
        return err(400, "session_id query parameter is required")
    session = sessions.get(session_id)
    if session is None:
        return err(404, f"session {session_id} is unknown")
    if session["report"] is None:
        return err(409, "the suite has not ended; retry the lookup later")
    return session["report"]
