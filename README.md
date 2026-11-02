# Documentation Tracker (Team 16, Pod 15/16)

ECE 30861 / CSCI 46500, Fall 2026. Read-only service that analyzes changes between two commits of a public GitHub repository, classifies each change, warns about missing or unchanged mapped documentation, and saves immutable JSON evidence, supporting technical-documentation upkeep under EU AI Act Article 53(1)(a) and Annex XI. Phase 4 implementation: `v0.4.0` (release/deployment verification required).

| Service | Base URL (register these) |
|---|---|
| System | `https://doc-tracker-team16.onrender.com/system` |
| Tester | `https://doc-tracker-team16.onrender.com/tester` |

Interactive API docs: `/system/docs`, `/tester/docs`. Machine-readable contracts: [`openapi/`](openapi/).

## Web workspace

Open [the homepage](https://doc-tracker-team16.onrender.com/) to analyze a public
repository, retrieve an analysis by ID, or run the tester against a compatible
system base URL. The page reads live health/version information, shows findings
and individual test outcomes, and downloads original JSON evidence. It also shows
code, component and system-model coverage returned by the tester. These are
observations from a run, not a declaration of complete contract conformance.

Use the sample-repository button for a deterministic public example, or supply
`owner/repository` and a head commit SHA (optionally a base SHA). A test target is
the exact system API base URL supplied by its team, including `/system` when used;
do not append `/docs`. Keep the page open during a suite run, save the session ID,
and download the resulting report. A session ID can recover a report after a
connection interruption while the service instance still exists.

Opening `/system` or `/tester` now redirects to the relevant interactive API docs;
the operation paths underneath those base URLs remain the same. `/info` provides
the machine-readable service links and version previously returned at `/`.

The free Render service may take about a minute to wake after inactivity. The
current deployment uses local evidence storage: analyses and in-memory tester
sessions can disappear on sleep, restart or redeployment. Download evidence before
leaving. Authorized review mutations and model-drift validation are not part of
this prose detector; all findings require human review.

## Quick start

```bash
pip install -r requirements-dev.txt
python -m pytest -q                       # offline unit/API/acceptance tests
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

## Phase 4 evidence

See [system models](docs/SYSTEM.md), [mapping investigation](docs/MAPPING_INVESTIGATION.md),
[validation](docs/VALIDATION.md) and [release steps](docs/RELEASE.md).
The co-change heuristic cannot prove that an edited document is correct.
Version 1 response-field corrections require clients of v0.3.0 to migrate.
