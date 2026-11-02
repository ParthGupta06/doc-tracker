"""In-process API tests for the system and tester (no network)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from doctracker.main import app
from doctracker.system import app as system_module
from doctracker.system.storage import LocalStore, StorageError
from doctracker.tester import app as tester_module

COMMITS = json.loads((Path(__file__).resolve().parents[1] / "doctracker/tester/commits.json").read_text())["commits"]
client = TestClient(app)
REPO = "pod/fixtures"


def analyze(**body: object) -> httpx.Response:
    return client.post("/system/analyze", json=body)


def test_analyze_success_and_retrieve() -> None:
    r = analyze(repository=REPO, commit_id=COMMITS["c1-impl-only"])
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "SUCCESS"
    assert body["base_commit"] == COMMITS["c0-initial"]
    assert body["changes"] == [{"path": "src/model.py", "old_path": None, "change_type": "MODIFIED",
                                "category": "IMPLEMENTATION"}]
    assert len(body["issues"]) == 2
    assert body["issues"][0]["issue_type"] == "OUTDATED_DOCUMENTATION"
    g = client.get(f"/system/analysis/{body['analysis_id']}")
    assert g.status_code == 200 and g.json() == body


def test_short_sha_resolves_to_full() -> None:
    r = analyze(repository=REPO, commit_id=COMMITS["c3-rename"][:10])
    assert r.status_code == 200
    assert r.json()["head_commit"] == COMMITS["c3-rename"]


@pytest.mark.parametrize(
    "payload",
    [
        {"repository": REPO},
        {"commit_id": "abcdef1"},
        {"repository": "bad format", "commit_id": "abcdef1"},
        {"repository": REPO, "commit_id": 1234567},
        {"repository": REPO, "commit_id": "xyz"},
        {"repository": REPO, "commit_id": "abcdef1", "base_commit": "nothex!"},
    ],
)
def test_invalid_requests_return_400(payload: dict[str, object]) -> None:
    r = client.post("/system/analyze", json=payload)
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_REQUEST"
    assert r.json()["message"]


def test_malformed_json_returns_400() -> None:
    r = client.post("/system/analyze", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400 and r.json()["code"] == "INVALID_REQUEST"


def test_missing_repo_and_commit_404() -> None:
    assert analyze(repository="pod/missing", commit_id="abcdef1").json()["code"] == "REPOSITORY_NOT_FOUND"
    r = analyze(repository=REPO, commit_id="0" * 40)
    assert r.status_code == 404 and r.json()["code"] == "COMMIT_NOT_FOUND"


@pytest.mark.parametrize("analysis_id", ["an-" + "0" * 32, "../../etc/passwd", "an-xyz"])
def test_unknown_analysis_404(analysis_id: str) -> None:
    r = client.get(f"/system/analysis/{analysis_id}")
    assert r.status_code == 404


def test_storage_failure_returns_500(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(self: LocalStore, analysis_id: str, result: dict[str, object]) -> None:
        raise StorageError("disk full")

    monkeypatch.setattr(LocalStore, "save", boom)
    r = analyze(repository=REPO, commit_id=COMMITS["c1-impl-only"])
    assert r.status_code == 500 and r.json()["code"] == "STORAGE_FAILED"


def test_read_failure_returns_contract_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(self: LocalStore, analysis_id: str) -> None:
        raise StorageError("read unavailable")

    monkeypatch.setattr(LocalStore, "load", boom)
    r = client.get('/system/analysis/an-' + '1' * 32)
    assert r.status_code == 500 and r.json()['code'] == 'STORAGE_FAILED'


def test_historical_results_are_returned_without_schema_migration(monkeypatch: pytest.MonkeyPatch) -> None:
    old = {'analysis_id': 'an-' + '1' * 32, 'tool_version': '0.3.0',
           'changes': [{'path': 'src/model.py', 'category': 'IMPLEMENTATION', 'change_type': 'MODIFIED'}]}
    monkeypatch.setattr(system_module.store, 'load', lambda aid: old)
    assert client.get('/system/analysis/' + old['analysis_id']).json() == old


def test_evidence_files_are_not_overwritten(tmp_path: Path) -> None:
    store = LocalStore(str(tmp_path))
    store.save("an-" + "1" * 32, {"a": 1})
    with pytest.raises(StorageError):
        store.save("an-" + "1" * 32, {"a": 2})
    assert store.load("an-" + "1" * 32) == {"a": 1}


def test_system_test_endpoints() -> None:
    assert client.post("/system/test/setup", json={"session_id": "unit-1", "setup": {}}).status_code == 201
    dup = client.post("/system/test/setup", json={"session_id": "unit-1", "setup": {}})
    assert dup.status_code == 409 and dup.json()["source"] == "system"
    bad = client.post("/system/test/setup", json={"setup": {}})
    assert bad.status_code == 400 and bad.json()["message"]
    analyze(repository=REPO, commit_id=COMMITS["c1-impl-only"])
    rep = client.get("/system/test/report", params={"session_id": "unit-1"})
    code = rep.json()["coverage"]["code"]
    assert rep.status_code == 200 and code["basis"]
    if code["covered"] is not None:
        assert 0 < code["covered"] <= code["total"]
    assert client.get("/system/test/report", params={"session_id": "nope"}).status_code == 404
    assert client.get("/system/test/report").status_code == 400


def test_tester_validation_and_unknown_sessions() -> None:
    assert client.post("/tester/test/setup", json={}).status_code == 400
    r = client.post("/tester/test/setup", json={"target_url": "https://x.example/system?q=1"})
    assert r.status_code == 400 and r.json()["source"] == "tester"
    assert client.post("/tester/test/run", json={"session_id": "missing"}).status_code == 404
    assert client.get("/tester/test/report", params={"session_id": "missing"}).status_code == 404
    assert client.get("/tester/test/report").status_code == 400


def test_full_suite_against_in_process_system(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the tester's whole suite against the system through an ASGI transport."""
    real = httpx.AsyncClient

    def asgi_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.ASGITransport(app=app)
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(tester_module.httpx, "AsyncClient", asgi_client)
    setup = client.post("/tester/test/setup", json={"target_url": "http://testserver/system"})
    assert setup.status_code == 201
    sid = setup.json()["session_id"]
    assert client.get("/tester/test/report", params={"session_id": sid}).status_code == 409
    run = client.post("/tester/test/run", json={"session_id": sid})
    assert run.status_code == 200
    report = run.json()
    ids = [r["test_id"] for r in report["results"]]
    assert len(ids) == len(set(ids)) == 33
    failed = [r for r in report["results"] if r["outcome"] not in ("pass", "skip")]
    assert failed == []
    assert report["coverage"]["system"] == {**report["coverage"]["system"], "covered": 8, "total": 10}
    assert client.post("/tester/test/run", json={"session_id": sid}).status_code == 409
    assert client.get("/tester/test/report", params={"session_id": sid}).json() == report
    assert sid in system_module.sessions
