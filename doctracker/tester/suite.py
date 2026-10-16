"""Team 16 test suite for the pod's Documentation Tracker project API.

Every planned test appears exactly once. Tests for acceptance criteria
scheduled for later phases are reported as `skip` with the reason.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

COMMITS: dict[str, str] = json.loads(Path(__file__).with_name("commits.json").read_text())["commits"]

COMPONENTS = {
    "C1": "Common web-service interface (validation, routing, error mapping)",
    "C2": "Read-only repository fetch and version resolution",
    "C3": "Change detection and classification",
    "C4": "Mapping and documentation rule detector",
    "C5": "Result builder and evidence persistence",
    "C6": "Saved-result retrieval",
    "C7": "Authorized review workflow",
}
ACCEPTANCE_CRITERIA = [f"AC-{i:02d}" for i in range(1, 11)]

SIGNIFICANT = ("repository", "head_commit", "base_commit", "status", "changes", "skipped")
RESULT_FIELDS = {
    "analysis_id": str, "repository": str, "head_commit": str, "config_version": str,
    "tool_version": str, "status": str, "issues": list, "changes": list, "skipped": list,
}


class Fail(Exception):
    pass


class SystemError_(Exception):
    pass


@dataclass
class Ctx:
    client: httpx.AsyncClient
    target: str
    fixture_repo: str
    memo: dict[str, Any] = field(default_factory=dict)

    async def post(self, path: str, body: Any = None, raw: str | None = None) -> httpx.Response:
        if raw is not None:
            return await self.client.post(self.target + path, content=raw,
                                          headers={"Content-Type": "application/json"})
        return await self.client.post(self.target + path, json=body)

    async def get(self, path: str) -> httpx.Response:
        return await self.client.get(self.target + path)


def body_of(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError as exc:
        raise Fail(f"HTTP {resp.status_code} response body is not JSON") from exc


def check_schema(result: Any) -> None:
    if not isinstance(result, dict):
        raise Fail("AnalysisResult is not a JSON object")
    for name, kind in RESULT_FIELDS.items():
        if not isinstance(result.get(name), kind):
            raise Fail(f"AnalysisResult.{name} missing or not {kind.__name__}")
    if result["status"] not in ("SUCCESS", "ERROR"):
        raise Fail(f"status {result['status']!r} is not SUCCESS or ERROR")
    for change in result["changes"]:
        for key in ("path", "change_type", "category"):
            if not isinstance(change.get(key), str):
                raise Fail(f"change entry missing string field {key}")
    for issue in result["issues"]:
        if issue.get("verification_status") != "PENDING_REVIEW":
            raise Fail("a new finding is not PENDING_REVIEW")


def normalized_changes(result: dict[str, Any]) -> list[tuple[str, str | None, str, str]]:
    return sorted((c["path"], c.get("old_path"), c["change_type"], c["category"]) for c in result["changes"])


async def analyze_ok(ctx: Ctx, commit: str, base: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"repository": ctx.fixture_repo, "commit_id": commit}
    if base:
        body["base_commit"] = base
    resp = await ctx.post("/analyze", body)
    if resp.status_code >= 500:
        raise SystemError_(f"POST /analyze returned HTTP {resp.status_code}: {resp.text[:200]}")
    if resp.status_code != 200:
        raise Fail(f"expected HTTP 200 from POST /analyze; received {resp.status_code}: {resp.text[:200]}")
    result: dict[str, Any] = body_of(resp)
    check_schema(result)
    if result["status"] != "SUCCESS":
        raise Fail(f"expected status SUCCESS; received {result['status']}")
    return result


def expect_changes(result: dict[str, Any], expected: list[tuple[str, str | None, str, str]]) -> str:
    actual = normalized_changes(result)
    if actual != sorted(expected):
        raise Fail(f"changes differ. Expected {sorted(expected)}; received {actual}")
    return f"Expected {len(expected)} classified change(s); received matching set."


async def expect_error(ctx: Ctx, resp: httpx.Response, status: int, code: str) -> str:
    if resp.status_code >= 500 and status < 500:
        raise SystemError_(f"expected HTTP {status} {code}; system failed with HTTP {resp.status_code}")
    body = body_of(resp)
    if resp.status_code != status or not isinstance(body, dict) or body.get("code") != code:
        raise Fail(f"expected HTTP {status} {code}; received HTTP {resp.status_code} {json.dumps(body)[:200]}")
    if not body.get("message"):
        raise Fail("error response has an empty message")
    return f"Expected HTTP {status} {code}; received HTTP {status} {code}."


# ---------------------------------------------------------------- tests

async def t01(ctx: Ctx) -> str:
    r = await analyze_ok(ctx, COMMITS["c1-impl-only"])
    ctx.memo["t01"] = r
    if r["base_commit"] != COMMITS["c0-initial"]:
        raise Fail(f"default base should be first parent {COMMITS['c0-initial']}; received {r['base_commit']}")
    return expect_changes(r, [("src/model.py", None, "MODIFIED", "IMPLEMENTATION")])


async def t02(ctx: Ctx) -> str:
    r = await analyze_ok(ctx, COMMITS["c2-add-mod-del"])
    return expect_changes(r, [
        ("docs/model.md", None, "MODIFIED", "OTHER"),
        ("src/eval.py", None, "ADDED", "IMPLEMENTATION"),
        ("src/train.py", None, "DELETED", "IMPLEMENTATION"),
    ])


async def t03(ctx: Ctx) -> str:
    r = await analyze_ok(ctx, COMMITS["c3-rename"])
    return expect_changes(r, [("src/evaluate.py", "src/eval.py", "RENAMED", "IMPLEMENTATION")])


async def t04(ctx: Ctx) -> str:
    r = await analyze_ok(ctx, COMMITS["c4-categories"])
    return expect_changes(r, [
        ("docs/architecture/overview.md", None, "MODIFIED", "ARCHITECTURE"),
        ("docs/design/decisions.md", None, "MODIFIED", "DESIGN"),
        ("requirements/REQUIREMENTS.md", None, "MODIFIED", "REQUIREMENT"),
        ("specs/api.yaml", None, "MODIFIED", "SPECIFICATION"),
    ])


async def t05(ctx: Ctx) -> str:
    r = await analyze_ok(ctx, COMMITS["c6-binary"])
    msg = expect_changes(r, [
        ("assets/logo.png", None, "MODIFIED", "OTHER"),
        ("data/weights.bin", None, "ADDED", "OTHER"),
    ])
    skipped = sorted((s.get("path"), s.get("reason")) for s in r["skipped"])
    expected = [("assets/logo.png", "UNSUPPORTED_FILE_TYPE"), ("data/weights.bin", "UNSUPPORTED_FILE_TYPE")]
    if skipped != expected:
        raise Fail(f"skipped differs. Expected {expected}; received {skipped}")
    return msg + " Both binary files listed as skipped."


async def t06(ctx: Ctx) -> str:
    r = await analyze_ok(ctx, COMMITS["c3-rename"], base=COMMITS["c0-initial"])
    if r["base_commit"] != COMMITS["c0-initial"]:
        raise Fail("explicit base_commit was not honored")
    return expect_changes(r, [
        ("docs/model.md", None, "MODIFIED", "OTHER"),
        ("src/evaluate.py", None, "ADDED", "IMPLEMENTATION"),
        ("src/model.py", None, "MODIFIED", "IMPLEMENTATION"),
        ("src/train.py", None, "DELETED", "IMPLEMENTATION"),
    ])


async def t07(ctx: Ctx) -> str:
    r = await analyze_ok(ctx, COMMITS["c0-initial"])
    if r["base_commit"] is not None:
        raise Fail(f"root commit should have base_commit null; received {r['base_commit']}")
    if len(r["changes"]) != 11 or any(c["change_type"] != "ADDED" for c in r["changes"]):
        raise Fail("root commit should report all 11 files as ADDED")
    return "Root commit analyzed against the empty tree; 11 ADDED changes and base_commit null."


async def t08(ctx: Ctx) -> str:
    resp = await ctx.post("/analyze", {"repository": ctx.fixture_repo})
    return await expect_error(ctx, resp, 400, "INVALID_REQUEST")


async def t09(ctx: Ctx) -> str:
    resp = await ctx.post("/analyze", raw='{"repository": "x/y", "commit_id": ')
    return await expect_error(ctx, resp, 400, "INVALID_REQUEST")


async def t10(ctx: Ctx) -> str:
    resp = await ctx.post("/analyze", {"repository": "not a repo", "commit_id": COMMITS["c1-impl-only"]})
    return await expect_error(ctx, resp, 400, "INVALID_REQUEST")


async def t11(ctx: Ctx) -> str:
    resp = await ctx.post("/analyze", {"repository": ctx.fixture_repo, "commit_id": 12345678})
    return await expect_error(ctx, resp, 400, "INVALID_REQUEST")


async def t12(ctx: Ctx) -> str:
    resp = await ctx.post("/analyze", {"repository": "pod15-16-nonexistent/does-not-exist-7f3a",
                                       "commit_id": COMMITS["c1-impl-only"]})
    return await expect_error(ctx, resp, 404, "REPOSITORY_NOT_FOUND")


async def t13(ctx: Ctx) -> str:
    resp = await ctx.post("/analyze", {"repository": ctx.fixture_repo, "commit_id": "0" * 40})
    return await expect_error(ctx, resp, 404, "COMMIT_NOT_FOUND")


async def t14(ctx: Ctx) -> str:
    first = ctx.memo.get("t01") or await analyze_ok(ctx, COMMITS["c1-impl-only"])
    resp = await ctx.get(f"/analysis/{first['analysis_id']}")
    if resp.status_code != 200:
        raise Fail(f"expected HTTP 200 retrieving saved analysis; received {resp.status_code}")
    saved = body_of(resp)
    if saved != first:
        raise Fail("retrieved analysis differs from the POST /analyze response")
    return "Saved AnalysisResult retrieved and identical to the original response."


async def t15(ctx: Ctx) -> str:
    resp = await ctx.get("/analysis/an-00000000000000000000000000000000")
    return await expect_error(ctx, resp, 404, "ANALYSIS_NOT_FOUND")


async def t16(ctx: Ctx) -> str:
    a = await analyze_ok(ctx, COMMITS["c2-add-mod-del"])
    b = await analyze_ok(ctx, COMMITS["c2-add-mod-del"])
    if a["analysis_id"] == b["analysis_id"]:
        raise Fail("two runs returned the same analysis_id; evidence would be overwritten")
    for run in (a, b):
        resp = await ctx.get(f"/analysis/{run['analysis_id']}")
        if resp.status_code != 200 or body_of(resp) != run:
            raise Fail(f"run {run['analysis_id']} was not retrievable unchanged")
    return "Two runs produced distinct analysis IDs; both retrievable unchanged."


async def t17(ctx: Ctx) -> str:
    runs = [await analyze_ok(ctx, COMMITS["c4-categories"]) for _ in range(5)]
    reference = {k: runs[0][k] for k in SIGNIFICANT}
    for i, run in enumerate(runs[1:], start=2):
        if {k: run[k] for k in SIGNIFICANT} != reference:
            raise Fail(f"run {i} differs from run 1 in significant fields")
        if [{k: v for k, v in f.items() if k != "finding_id"} for f in run["issues"]] != \
           [{k: v for k, v in f.items() if k != "finding_id"} for f in runs[0]["issues"]]:
            raise Fail(f"run {i} findings differ from run 1")
    return "Five repeated runs returned identical significant fields and schema-valid results."


TestFn = Callable[[Ctx], Awaitable[str]]


@dataclass(frozen=True)
class TestCase:
    test_id: str
    title: str
    criteria: tuple[str, ...]
    components: tuple[str, ...]
    fn: TestFn | None
    skip_reason: str | None = None


PIPELINE = ("C1", "C2", "C3", "C5")

TESTS: list[TestCase] = [
    TestCase("T-01", "Implementation-only change, default base", ("AC-01",), PIPELINE, t01),
    TestCase("T-02", "Added, modified and deleted files", ("AC-01",), PIPELINE, t02),
    TestCase("T-03", "Rename detection", ("AC-01",), PIPELINE, t03),
    TestCase("T-04", "Requirement/specification/design/architecture categories", ("AC-01",), PIPELINE, t04),
    TestCase("T-05", "Unsupported binary files are skipped", ("AC-01",), PIPELINE, t05),
    TestCase("T-06", "Explicit base_commit across several commits", ("AC-01",), PIPELINE, t06),
    TestCase("T-07", "Root commit boundary", ("AC-01",), PIPELINE, t07),
    TestCase("T-08", "Missing commit_id", ("AC-07",), ("C1",), t08),
    TestCase("T-09", "Malformed JSON", ("AC-07",), ("C1",), t09),
    TestCase("T-10", "Invalid repository format", ("AC-07",), ("C1",), t10),
    TestCase("T-11", "Incorrectly typed commit_id", ("AC-07",), ("C1",), t11),
    TestCase("T-12", "Nonexistent repository", ("AC-08",), ("C1", "C2"), t12),
    TestCase("T-13", "Nonexistent commit", ("AC-08",), ("C1", "C2"), t13),
    TestCase("T-14", "Retrieve saved analysis", ("AC-06",), ("C1", "C6"), t14),
    TestCase("T-15", "Unknown analysis_id", ("AC-06", "AC-08"), ("C1", "C6"), t15),
    TestCase("T-16", "Distinct, durable run files", ("AC-06",), PIPELINE + ("C6",), t16),
    TestCase("T-17", "Five-run repeatability", ("AC-10",), PIPELINE, t17),
    TestCase("T-18", "Missing mapped documentation finding", ("AC-02",), ("C4",), None,
             "Documentation detection is the Phase 4 milestone (Phase 2, Section 6.2)."),
    TestCase("T-19", "Unchanged mapped documentation finding", ("AC-02",), ("C4",), None,
             "Documentation detection is the Phase 4 milestone (Phase 2, Section 6.2)."),
    TestCase("T-20", "Code and documentation updated together", ("AC-03",), ("C4",), None,
             "Documentation detection is the Phase 4 milestone (Phase 2, Section 6.2)."),
    TestCase("T-21", "New findings start PENDING_REVIEW", ("AC-04",), ("C4", "C5"), None,
             "Requires findings from the Phase 4 detector."),
    TestCase("T-22", "Authorized and unauthorized review decisions", ("AC-05",), ("C7",), None,
             "Review workflow is the Phase 5 milestone (Phase 2, Section 6.3)."),
    TestCase("T-23", "Read-only analysis, no repository code execution", ("AC-09",), ("C2",), None,
             "Requires source comparison and code inspection; scheduled for Phase 5."),
]
