"""Prints the Phase 3 Q3.1 operation-status table by probing a deployed system.

Usage: python scripts/contract_status.py https://HOST/system  (or SYSTEM_BASE_URL env var)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

COMMITS = json.loads((Path(__file__).resolve().parents[1] / "doctracker/tester/commits.json").read_text())["commits"]
REPO = os.environ.get("FIXTURE_REPO", "OWNER/doc-tracker-fixtures")


def check(ok: bool) -> str:
    return "yes" if ok else "no"


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else os.environ["SYSTEM_BASE_URL"]).rstrip("/")
    rows = []
    with httpx.Client(timeout=120) as c:
        ok = c.post(f"{base}/analyze", json={"repository": REPO, "commit_id": COMMITS["c1-impl-only"]})
        bad = c.post(f"{base}/analyze", json={"repository": REPO})
        missing = c.post(f"{base}/analyze", json={"repository": REPO, "commit_id": "0" * 40})
        succ = ok.status_code == 200 and ok.json().get("status") == "SUCCESS"
        errs = bad.status_code == 400 and bad.json().get("code") == "INVALID_REQUEST" and missing.status_code == 404
        rows.append(("POST /analyze", "REQ-01, REQ-04, REQ-05, REQ-07", succ, errs))
        aid = ok.json().get("analysis_id") if succ else "an-" + "0" * 32
        got = c.get(f"{base}/analysis/{aid}")
        unk = c.get(f"{base}/analysis/an-{'0' * 32}")
        rows.append(("GET /analysis/{analysis_id}", "REQ-04, REQ-07", got.status_code == 200 and got.json() == ok.json(),
                     unk.status_code == 404 and unk.json().get("code") == "ANALYSIS_NOT_FOUND"))
        sid = f"contract-{os.getpid()}"
        st = c.post(f"{base}/test/setup", json={"session_id": sid, "setup": {}})
        dup = c.post(f"{base}/test/setup", json={"session_id": sid, "setup": {}})
        rows.append(("POST /test/setup", "testing interface", st.status_code == 201 and st.json() == {"session_id": sid},
                     dup.status_code == 409 and bool(dup.json().get("message"))))
        rp = c.get(f"{base}/test/report", params={"session_id": sid})
        rn = c.get(f"{base}/test/report", params={"session_id": "unknown-session"})
        rows.append(("GET /test/report", "testing interface", rp.status_code == 200 and "code" in rp.json().get("coverage", {}),
                     rn.status_code == 404))
    for op, reqs, s, e in rows:
        print(f"{op} | Requirement(s): {reqs} | Implemented: yes")
        print(f"  Success responses conform: {check(s)} | Error responses conform: {check(e)}")
    return 0 if all(s and e for _, _, s, e in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
