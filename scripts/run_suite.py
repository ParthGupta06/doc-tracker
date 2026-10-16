"""Runs a tester against a target system through the course testing interface.

Usage:
  python scripts/run_suite.py --tester https://HOST/tester --target https://HOST/system [--out report.json]

Base URLs come from arguments or the TESTER_BASE_URL / TARGET_BASE_URL environment
variables, so a grader can point the suite at any team without editing code.
Exits non-zero when setup fails or the report is malformed (not when tests fail).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

import httpx

OUTCOMES = {"pass", "fail", "error", "skip"}
SOURCES = {"tester", "system", "communication", "unknown"}


def well_formed(report: dict) -> list[str]:
    problems = []
    ids = [r.get("test_id") for r in report.get("results", [])]
    if len(ids) != len(set(ids)) or not all(ids):
        problems.append("test_id values must be unique and nonempty")
    for r in report.get("results", []):
        if r.get("outcome") not in OUTCOMES:
            problems.append(f"{r.get('test_id')}: bad outcome {r.get('outcome')}")
        if not r.get("message"):
            problems.append(f"{r.get('test_id')}: empty message")
        if r.get("outcome") == "error" and r.get("source") not in SOURCES:
            problems.append(f"{r.get('test_id')}: error without valid source")
    for key in ("code", "component", "system"):
        c = report.get("coverage", {}).get(key)
        if not isinstance(c, dict) or not c.get("basis"):
            problems.append(f"coverage.{key} missing or without basis")
            continue
        cov, tot = c.get("covered"), c.get("total")
        if (cov is None) != (tot is None):
            problems.append(f"coverage.{key}: covered/total must both be null or both integers")
        elif cov is not None and not (0 <= cov <= tot):
            problems.append(f"coverage.{key}: covered must be between 0 and total")
    return problems


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tester", default=os.environ.get("TESTER_BASE_URL"))
    p.add_argument("--target", default=os.environ.get("TARGET_BASE_URL"))
    p.add_argument("--out")
    p.add_argument("--timeout", type=float, default=600)
    a = p.parse_args()
    if not a.tester or not a.target:
        p.error("--tester and --target (or TESTER_BASE_URL / TARGET_BASE_URL) are required")
    with httpx.Client(timeout=a.timeout) as c:
        s = c.post(f"{a.tester.rstrip('/')}/test/setup", json={"target_url": a.target})
        print(f"setup -> HTTP {s.status_code} {s.text}")
        if s.status_code != 201:
            return 2
        sid = s.json()["session_id"]
        r = c.post(f"{a.tester.rstrip('/')}/test/run", json={"session_id": sid})
        if r.status_code != 200:
            print(f"run -> HTTP {r.status_code} {r.text}; fetching stored report")
            r = c.get(f"{a.tester.rstrip('/')}/test/report", params={"session_id": sid})
        report = r.json()
    counts = Counter(x["outcome"] for x in report.get("results", []))
    print(f"session {sid}: run={len(report.get('results', []))} " +
          " ".join(f"{k}={counts.get(k, 0)}" for k in ("pass", "fail", "error", "skip")))
    for x in report.get("results", []):
        if x["outcome"] in ("fail", "error"):
            print(f"  {x['test_id']} {x['outcome']}: {x['message']}")
    for k, v in report.get("coverage", {}).items():
        print(f"  coverage.{k}: {v.get('covered')}/{v.get('total')}")
    if a.out:
        with open(a.out, "w") as fh:
            json.dump(report, fh, indent=2)
    problems = well_formed(report)
    for prob in problems:
        print(f"MALFORMED: {prob}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
