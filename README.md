# Documentation Tracker (Team 16, Pod 15/16)

ECE 30861 / CSCI 46500, Fall 2026. Read-only service that analyzes changes between two commits of a public GitHub repository, classifies each change, and saves immutable JSON evidence, supporting technical-documentation upkeep under EU AI Act Article 53(1)(a) and Annex XI. Phase 3 increment: `v0.3.0`.

| Service | Base URL (register these) |
|---|---|
| System | `https://<render-host>/system` |
| Tester | `https://<render-host>/tester` |

Interactive API docs: `/system/docs`, `/tester/docs`. Machine-readable contracts: [`openapi/`](openapi/).

## Quick start

```bash
pip install -r requirements-dev.txt
pytest                                   # 40 tests, offline (builds the fixture repo locally)
uvicorn doctracker.main:app --port 8000  # system at /system, tester at /tester
```

Run our tester against any system (no code edits; base URLs are arguments or env vars):

```bash
python scripts/run_suite.py --tester https://<host>/tester --target https://<other-team>/system
python scripts/contract_status.py https://<host>/system   # prints the operation-status table
```

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `FIXTURE_REPO` | Public fixture repository (`owner/name`) the tester analyzes | `OWNER/doc-tracker-fixtures` |
| `EVIDENCE_REPO`, `EVIDENCE_TOKEN` | Durable evidence storage via GitHub contents API (fine-grained PAT, contents read/write on that repo only) | unset: local files |
| `EVIDENCE_DIR` | Local evidence directory | `data/runs` |
| `TESTER_SETUP_TIMEOUT`, `TESTER_CALL_TIMEOUT` | Seconds | 90, 90 |

## Fixture repository

`fixtures/build_fixture_repo.py` builds the shared fixture repo with fixed authors and timestamps, so SHAs are identical everywhere. Expected SHAs live in [`doctracker/tester/commits.json`](doctracker/tester/commits.json). Push once:

```bash
python fixtures/build_fixture_repo.py build/fixtures
cd build/fixtures && git remote add origin https://github.com/<owner>/doc-tracker-fixtures.git
git push -u origin main --tags
```

See [`docs/SYSTEM.md`](docs/SYSTEM.md) for models, interface, session rules and known limitations.
