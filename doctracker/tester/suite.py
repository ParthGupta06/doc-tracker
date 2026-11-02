"""Team 16 test suite for the pod's Documentation Tracker project API.

Every planned test appears exactly once. Tests for acceptance criteria
scheduled for later phases are reported as `skip` with the reason.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from jsonschema import ValidationError

from doctracker.tester.contract import ROOT, validate

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

SIGNIFICANT = ("head_commit", "base_commit", "config_version", "status", "error", "changes", "skipped", "unmapped")
GOLDEN = {c['case']: c for c in json.loads((ROOT / 'docs/contract/golden-outputs.json').read_text())['cases']}


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
    answered: bool = False

    async def post(self, path: str, body: Any = None, raw: str | None = None) -> httpx.Response:
        if raw is not None:
            response = await asyncio.wait_for(self.client.post(self.target + path, content=raw,
                                              headers={"Content-Type": "application/json"}), 90.0)
        else:
            response = await asyncio.wait_for(self.client.post(self.target + path, json=body), 90.0)
        self.answered = True
        return response

    async def get(self, path: str) -> httpx.Response:
        response = await asyncio.wait_for(self.client.get(self.target + path), 90.0)
        self.answered = True
        if response.status_code >= 500:
            raise SystemError_(f'GET {path} returned HTTP {response.status_code}')
        return response


def body_of(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError as exc:
        raise Fail(f"HTTP {resp.status_code} response body is not JSON") from exc


def check_schema(result: Any) -> None:
    try:
        validate(result, 'AnalysisResult')
    except ValidationError as exc:
        raise Fail(f"pod AnalysisResult schema: {exc.message}") from exc


def without_explanations(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in f.items() if k != 'explanation'} for f in issues]


def compare_golden(result: dict[str, Any], case: str, findings: bool = False) -> None:
    expected = GOLDEN[case]['expected']
    for key in SIGNIFICANT:
        if result[key] != expected[key]:
            raise Fail(f"{case}: {key} differs from pinned golden output")
    if findings and without_explanations(result['issues']) != without_explanations(expected['issues']):
        raise Fail(f"{case}: findings differ from pinned golden output")


async def golden_case(ctx: Ctx, case: str, findings: bool = False) -> dict[str, Any]:
    request = GOLDEN[case]['request']
    r = await analyze_ok(ctx, request['commit_id'], request.get('base_commit'))
    compare_golden(r, case, findings)
    return r


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
    ctx.memo['t01'] = await golden_case(ctx, 'c1-impl-only')
    return 'Shared fields match golden output.'


async def t02(ctx: Ctx) -> str:
    await golden_case(ctx, 'c2-add-mod-del')
    return 'Shared fields match golden output.'


async def t03(ctx: Ctx) -> str:
    await golden_case(ctx, 'c3-rename')
    return 'Rename fields match golden output.'


async def t04(ctx: Ctx) -> str:
    await golden_case(ctx, 'c4-categories')
    return 'Categories match golden output.'


async def t05(ctx: Ctx) -> str:
    await golden_case(ctx, 'c6-binary')
    return 'Unsupported paths match golden output.'


async def t06(ctx: Ctx) -> str:
    await golden_case(ctx, 'c0-to-c3-explicit-base')
    return 'Explicit base and all shared fields match golden output.'


async def t07(ctx: Ctx) -> str:
    await golden_case(ctx, 'c0-initial')
    return 'Root result matches golden output.'


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
    for case in ('c4-categories', 'c1-impl-only'):
        runs = [await golden_case(ctx, case) for _ in range(5)]
        reference = {k: runs[0][k] for k in SIGNIFICANT}
        if any({k: r[k] for k in SIGNIFICANT} != reference for r in runs):
            raise Fail(f'{case}: significant shared fields differ across five runs')
    return 'Five runs each of c4 and c1 match the golden shared fields.'


async def t18(ctx: Ctx) -> str:
    ctx.memo['t18'] = await golden_case(ctx, 'c8-missing-doc', findings=True)
    return 'Missing-document findings match golden output including stable IDs.'


async def t19(ctx: Ctx) -> str:
    ctx.memo['t19'] = await golden_case(ctx, 'c1-impl-only', findings=True)
    return 'Outdated-document and undocumented-symbol findings match golden output.'


async def t20(ctx: Ctx) -> str:
    await golden_case(ctx, 'c7-code-and-doc', findings=True)
    return 'Correct co-update produces no findings.'


async def t21(ctx: Ctx) -> str:
    for case in ('c8-missing-doc', 'c1-impl-only'):
        r = await golden_case(ctx, case, findings=True)
        if not r['issues'] or any(f['verification_status'] != 'PENDING_REVIEW' for f in r['issues']):
            raise Fail('expected nonempty pending findings')
    return 'Both missing and stale cases produce only pending findings.'


TestFn = Callable[[Ctx], Awaitable[str]]


@dataclass(frozen=True)
class TestCase:
    test_id: str
    title: str
    criteria: tuple[str, ...]
    components: tuple[str, ...]
    fn: TestFn | None
    skip_reason: str | None = None
    feature: str | None = None


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
    TestCase("T-18", "Missing mapped documentation finding", ("AC-02",), ("C4",), t18, feature="prose_detector"),
    TestCase("T-19", "Unchanged mapped documentation finding", ("AC-02",), ("C4",), t19, feature="prose_detector"),
    TestCase("T-20", "Code and documentation updated together", ("AC-03",), ("C4",), t20, feature="prose_detector"),
    TestCase("T-21", "New findings start PENDING_REVIEW", ("AC-04",), ("C4", "C5"), t21, feature="prose_detector"),
    TestCase("T-22", "Authorized and unauthorized review decisions", ("AC-05",), ("C7",), None, "Phase 5"),
    TestCase("T-23", "Read-only analysis, no repository code execution", ("AC-09",), ("C2",), None, "checked by inspection"),
]

# v2.4.0 publishes no model fixture/oracles. Never invent results or test requests.
for number in range(24, 34):
    TESTS.append(TestCase(f"T-{number}", "Model drift (pending oracle)",
                         ("AC-08",) if number == 32 else (("AC-10",) if number == 33 else
                         (("AC-03",) if number in (24, 25, 29) else ("AC-02",))),
                         ("C1", "C2", "C4") if number == 33 else ("C1", "C2", "C3", "C4", "C5"),
                         None, "expected answers not yet published", "model_drift"))
