# Pod 15/16 contract: testing rules

Version 2.4.0, proposed 2026-10-31 and pending Team 16's agreement (section 10); no earlier version was agreed. Both teams' registry rows link this file as the intra-pod
specification. The course's `docs/base/student-facing-spec.docx.pdf` wins over every
file here.

**For graders.** Team 15's system has no prose detector, by design (section 1, deviation
1): its `issues` is always `[]`, and its `GET /health` lists `features: ["model_drift"]`.
So against `golden-outputs.json` it differs only in `issues`, on the cases that expect
findings: `c1-impl-only`, `c2-add-mod-del`, `c8-missing-doc` and
`c0-to-c3-explicit-base`. It also adds `drift` and `drift_error`, which are not
compared. Compare everything else as section 3 says.

| File (this folder) | Holds |
| --- | --- |
| `pod-contract.md` | testing rules: sessions, fixtures, test list, coverage, limits, errors, changes |
| `spec-v1.1.md` | Team 16's v1.1 specification: requirements, pipeline, prose detector, fixture, comparison rules, acceptance criteria |
| `pod-contract.openapi.yml` | the system API: routes, fields, enums, status codes |
| `pod-tester.openapi.yml` | the tester API and suite report, as fixed by the course |
| `mapping-v1.1.yaml` | shared classification rules, skip allowlist and code-to-doc mappings, loaded at runtime |
| `golden-outputs.json` | expected answers for the 10 cases on Team 16's fixture |
| `model-golden-outputs.json` | expected answers for T-24 to T-33 (pending, see section 3) |

`spec-v1.1.md` (the package's `SPEC.md`), `mapping-v1.1.yaml` and `golden-outputs.json`
are byte-identical copies from Team 16's v1.1 package (proposed 2026-10-30). "v1.1 SPEC"
in this folder means `spec-v1.1.md`. In it, read `openapi-system-v1.1.yaml` as
`pod-contract.openapi.yml`; where the two differ, this contract wins (section 9).

## 1. What is shared

This contract follows Team 16's v1.1 package with two deviations in behavior, below;
section 9 lists every difference. Team 16's system needs one change, section 2's
one-session rule. Team 16's tester needs seven changes:

- It reads `features` from `GET /health` once and skips as below.
- When `/health` fails, it marks only the tests that need a feature `error` (section 4).
- It accepts `drift` and `drift_error` in an `AnalysisResult`.
- It runs T-24 to T-33 against `model-golden-outputs.json` as each group is published
  (sections 3 and 4).
- It reports T-22 and T-23 as `skip` with the messages in section 4.
- It counts coverage only from tests the target answered (section 5).
- It keeps to section 6's limits: 110 s for system setup, 15 s for the system's
  `GET /test/report`, and a stop at 570 s of the 600 s run.

1. **No prose detector required.** `issues` is filled by the v1.1 SPEC section 6
   detector on a system that has one (Team 16). On a system without it (Team 15),
   `issues` is always `[]`, because Team 15's documentation is the `/models` folder,
   not prose files.
2. **Optional model-drift additions.** Team 15's `AnalysisResult` adds `drift` and
   `drift_error`, and Team 15 serves `POST /generate`. A tester never requires them.

**Features.** A system names what it implements in `GET /health` as `features`:
`prose_detector` (deviation 1) and `model_drift` (deviation 2). A system without the
field is treated as `["prose_detector"]`, as in v1.1. A tester never fails a system for
lacking a feature it does not list: each test that needs a missing feature is `skip`
with the message "target does not implement <feature>".

Team 15's `/analyze` runs the model check on every request. A commit with no `/models`
gives `status: "SUCCESS"`, `drift: null` and
`drift_error: {"code": "MODELS_NOT_FOUND", ...}`. `drift` and `drift_error` do not depend
on `status`: the model check runs even when `status` is `ERROR`. A drifted commit, beside
the shared fields:

```json
"drift": {
  "aligned": false,
  "behavioral": [],
  "ownership": [],
  "structural": [
    {"change": "ADDED", "file": "src/shop/orders.py", "id": "shop.orders:Order.cancel", "kind": "method"}
  ]
},
"drift_error": null
```

Saved results are durable: `GET /analysis/{analysis_id}` returns a result unchanged,
also after the system restarts or is redeployed.

## 2. Sessions, setup and cleanup

- System setup takes `{"session_id": "...", "setup": {}}`. Project requests do not carry
  the session id.
- **One active session at a time**, so sessions cannot interfere (course spec, session
  state and concurrency). System setup answers 409 for a session id that already exists,
  and for a new id while another session is active (message "another test session is
  active", source `system`). A session stays active until the next setup is accepted. A new setup is accepted once the active session's
  `GET /test/report` has been read (the tester's last call, course spec), or 720 s after
  the active session's setup: tester setup (120 s) plus tester run (600 s).
- Code coverage counts the lines run while the session is active, so it covers only that
  session's requests. Its report stays readable after the next session starts.
- **No resets and no cleanup:** the fixture repositories are public, fixed and only read.
- **After an interruption:** a restart clears sessions and tester reports (saved
  analysis results stay). The tester then starts a new session; it never reuses an id.
  Without a restart, the new session's setup answers 409 until the earlier session's
  report is read or its 720 s have passed.

## 3. Fixtures and expected answers

| Repository | Built by | Used by | Expected answers |
| --- | --- | --- | --- |
| `ParthGupta06/doc-tracker-fixtures` (c0 to c8) | Team 16 | T-01 to T-21 | `golden-outputs.json` |
| `MuhammadSban/doc-tracker-model-fixtures` | Team 15 | T-24 to T-33 | `model-golden-outputs.json` (pending) |

**Comparing with `golden-outputs.json`** (as v1.1 SPEC section 9): these fields must be
equal: `head_commit`, `base_commit`, `config_version`, `status`, `error`, `changes`,
`skipped`, `unmapped`, and `issues` with each finding's `explanation` removed. Not
compared: `analysis_id`, `repository` casing, `tool_version`, `created_at`,
`explanation`, `drift`, `drift_error`.

**`issues` is judged only in T-18 to T-21.** T-01 to T-17 compare every other field
above, so they run the same on every system.

**`model-golden-outputs.json`** uses the same layout as `golden-outputs.json`: one entry
per case with `case`, `request` and `expected`, where `expected` holds `drift` and
`drift_error` (and, for T-33, the texts of `structural.json`, `behavioral.json` and
`scope.json`).

Commits of the model fixture, oldest first:

| Tag | What the commit does | SHA |
| --- | --- | --- |
| L-pre | Python code, no `/models` yet | pending |
| L0 | `/models` committed as `drifter init` writes it | pending |
| L1 | comments and whitespace only | pending |
| L2 | adds one function | pending |
| L3 | removes one import | pending |
| L4 | adds a state and a transition into it | pending |
| L5 | L2's kind of change plus updated `/models` in the same commit | pending |
| L6 | a non-owner edits an owned path | pending |
| L7 | a hand edit removes an `inherits` edge from `structural.json` that the code still makes | pending |

**Publishing the expected answers** (Team 15). The drift tests are published in two groups, each once the
commits its tests use are fixed for good:

| Group | Tests | Commits used | Can be fixed when |
| --- | --- | --- | --- |
| 1 | T-32 | L-pre, which has no `/models` | the repository exists |
| 2 | T-24 to T-31, T-33 | L0 to L7, which commit all four model files | Team 15's specification settles the behavioral format and the scope rules (its open question Q11); the structural format is settled |

For each group:

- [ ] Fill the SHAs of the commits its tests use in the table above.
- [ ] Add its tests' expected answers to `model-golden-outputs.json`.
- [ ] Remove "pending" from its tests in section 4.
- [ ] Bump the version (section 10).

## 4. Test list

Both testers run every test, T-01 to T-33, so each tester checks both systems' detectors.
T-24 to T-33 are **pending** until their group is published (section 3); a pending test
is reported as `skip` with the message "expected answers not yet published".

The tester reads `GET /health` once before the first test. If it gives no 200 `Health`
body within 90 s, the target's features are unknown: each test that needs a feature
(T-18 to T-21, T-24 to T-33) is `error`, with source `communication` when nothing
answered and `system` otherwise; a pending test stays `skip`, and the other tests run as
usual. The last two columns say what a test does on a system without `prose_detector` or
without `model_drift` (section 1, Features). No test is expected to fail on either team's system.

Components and criteria per test are what counts toward coverage (section 5). For
T-01 to T-23 they are the lists Team 16's tester already uses.

| Test | Title | Golden case or request | Components | Criteria | Without `prose_detector` | Without `model_drift` |
| --- | --- | --- | --- | --- | --- | --- |
| T-01 | Implementation-only change, default base | c1-impl-only | C1 C2 C3 C5 | AC-01 | runs | runs |
| T-02 | Added, modified and deleted files | c2-add-mod-del | C1 C2 C3 C5 | AC-01 | runs | runs |
| T-03 | Rename detection | c3-rename | C1 C2 C3 C5 | AC-01 | runs | runs |
| T-04 | Requirement/specification/design/architecture categories | c4-categories | C1 C2 C3 C5 | AC-01 | runs | runs |
| T-05 | Unsupported binary files are skipped | c6-binary | C1 C2 C3 C5 | AC-01 | runs | runs |
| T-06 | Explicit base_commit across several commits | c0-to-c3-explicit-base | C1 C2 C3 C5 | AC-01 | runs | runs |
| T-07 | Root commit boundary | c0-initial | C1 C2 C3 C5 | AC-01 | runs | runs |
| T-08 | Missing commit_id | 400 `INVALID_REQUEST` | C1 | AC-07 | runs | runs |
| T-09 | Malformed JSON | 400 `INVALID_REQUEST` | C1 | AC-07 | runs | runs |
| T-10 | Invalid repository format | 400 `INVALID_REQUEST` | C1 | AC-07 | runs | runs |
| T-11 | Incorrectly typed commit_id | 400 `INVALID_REQUEST` | C1 | AC-07 | runs | runs |
| T-12 | Nonexistent repository | 404 `REPOSITORY_NOT_FOUND` | C1 C2 | AC-08 | runs | runs |
| T-13 | Nonexistent commit | 404 `COMMIT_NOT_FOUND` | C1 C2 | AC-08 | runs | runs |
| T-14 | Retrieve saved analysis | c1: GET equals the POST body | C1 C6 | AC-06 | runs | runs |
| T-15 | Unknown analysis_id | 404 `ANALYSIS_NOT_FOUND` | C1 C6 | AC-06 AC-08 | runs | runs |
| T-16 | Distinct, durable run files | c2 twice: two ids, both read back | C1 C2 C3 C5 C6 | AC-06 | runs | runs |
| T-17 | Five-run repeatability | c4 and c1, five runs each: identical compared fields | C1 C2 C3 C5 | AC-10 | runs | runs |
| T-18 | Missing mapped documentation finding | c8: `MISSING_DOCUMENTATION` | C4 | AC-02 | skip | runs |
| T-19 | Unchanged mapped documentation finding | c1: `OUTDATED_DOCUMENTATION`, `UNDOCUMENTED_SYMBOL` | C4 | AC-02 | skip | runs |
| T-20 | Code and documentation updated together | c7: `issues: []` | C4 | AC-03 | skip | runs |
| T-21 | New findings start PENDING_REVIEW | the findings of T-18 and T-19 | C4 C5 | AC-04 | skip | runs |
| T-22 | Authorized and unauthorized review decisions | Phase 5 | C7 | AC-05 | skip | skip |
| T-23 | Read-only analysis, no repository code execution | inspection | C2 | AC-09 | skip | skip |
| T-24 | `/analyze` at L0: `aligned: true`, three empty lists (pending) | model fixture | C1 C2 C3 C4 C5 | AC-03 | runs | skip |
| T-25 | `/analyze` at L1: `aligned: true` (pending) | model fixture | C1 C2 C3 C4 C5 | AC-03 | runs | skip |
| T-26 | `/analyze` at L2: one structural `ADDED` (pending) | model fixture | C1 C2 C3 C4 C5 | AC-02 | runs | skip |
| T-27 | `/analyze` at L3: one structural `REMOVED` (pending) | model fixture | C1 C2 C3 C4 C5 | AC-02 | runs | skip |
| T-28 | `/analyze` at L4: behavioral `ADDED` state and transition (pending) | model fixture | C1 C2 C3 C4 C5 | AC-02 | runs | skip |
| T-29 | `/analyze` at L5: `aligned: true` (pending) | model fixture | C1 C2 C3 C4 C5 | AC-03 | runs | skip |
| T-30 | `/analyze` at L6: one ownership `VIOLATION` (pending) | model fixture | C1 C2 C3 C4 C5 | AC-02 | runs | skip |
| T-31 | `/analyze` at L7: one structural `ADDED` (pending) | model fixture | C1 C2 C3 C4 C5 | AC-02 | runs | skip |
| T-32 | `/analyze` at L-pre: `drift: null`, `drift_error.code` `MODELS_NOT_FOUND` (pending) | model fixture | C1 C2 C3 C4 C5 | AC-08 | runs | skip |
| T-33 | `/generate` at L0: `structural.json`, `behavioral.json` and `scope.json` byte-equal to the committed `/models` (pending) | model fixture | C1 C2 C4 | AC-10 | runs | skip |

The "skip" cells in the last two columns are deviations 1 and 2: Team 15's system has no
`prose_detector`, and Team 16's has no `model_drift`. T-22 and T-23 are `skip` on every
system, with the messages "Phase 5" and "checked by inspection".

Rules for T-24 to T-33:

- **What is compared:** T-24 to T-31 compare the whole `drift` object with the expected
  one (same keys, same differences, same order) and require `drift_error: null`.
  T-32 compares `drift` and `drift_error.code`. T-33 compares the text of those three
  files exactly; `ownership.json` is not compared, because people correct it by hand
  after `drifter init` proposes it (Team 15's specification, section 3.2).
- **Skip:** when the system does not list `model_drift` (section 1, Features).
- **Otherwise** the course outcomes apply: a 5xx is `error` with source `system`, a
  timeout is `error` with source `communication`.

## 5. Coverage

Both testers use the same lists, so totals match.

- **Components (7):** C1 interface, C2 fetch and resolve, C3 diff and classify, C4
  detector (Team 16's prose detector, Team 15's model check), C5 result builder and
  persistence, C6 retrieval, C7 review workflow (Phase 5).
- **Criteria (10):** v1.1 SPEC section 10, copied word for word below without its
  Requirement column. For a system with `model_drift`, "doc" means `/models` and a
  finding means a drift difference. The tests that exercise each criterion are those
  listing it in section 4.

| AC | Check | Golden / fixture |
|---|---|---|
| AC-01 | `changes` and `skipped` equal golden | all cases |
| AC-02 | Missing and outdated docs flagged | c8, c1 |
| AC-03 | Code and doc updated together gives no finding | c7 |
| AC-04 | Every finding is PENDING_REVIEW | any case with issues |
| AC-05 | Authorized review decisions | Phase 5 |
| AC-06 | Two runs give distinct ids; GET returns each unchanged, including after a restart | c2 |
| AC-07 | Missing commit_id, malformed JSON, bad repository format, wrong type → 400 INVALID_REQUEST | n/a |
| AC-08 | Nonexistent repo/commit → 404; unknown analysis_id → 404; mapping problem → saved ERROR | n/a |
| AC-09 | Repository unchanged, no code executed, no credentials in logs | inspection, Phase 5 |
| AC-10 | Five runs of c4 and of c1 give identical significant fields, including identical finding_ids | c4, c1 |

- **What counts:** a component or criterion is covered when at least one test that sent
  its project calls and got an answer from the target lists it in section 4: outcome
  `pass` or `fail`, or `error` with source `system`. A test covers nothing when it is
  `skip`, `error` because `/health` failed (section 4), or `error` with any other source.
- **Code coverage** comes from the system's `GET /test/report`; `null` counts with a
  basis when unavailable, never 0.

## 6. Limits and retries

| Limit | Seconds |
| --- | --- |
| Tester setup (includes system setup and a cold start of the target) | 120 |
| Tester run | 600 |
| System setup | 90 |
| One project call, including Team 15's model check | 90 |
| Tester's wait for system setup, inside tester setup | 110 |
| Tester's read of the system's `GET /test/report` | 15 |
| Tester's read of the system's `GET /health`, once per run (section 4) | 90 |

With no answer from system setup within 110 s, tester setup answers 500 with source
`communication`. With no answer from the system's `GET /test/report` within 15 s, or an
error, the report's code coverage is `null` with a basis that says why.

**No retries.** A tester sends each project call once. A call with no response within
90 s is `error` with source `communication`; the tester does not resend it.

**Run limit.** At 570 s into its run, 30 s inside the 600 s limit, a tester aborts, as
the course spec defines an abort: it abandons the call in progress, sends no more project
calls, still reads the system's `GET /test/report` for code coverage (which also frees the
system for the next session, section 2), stores the available results and answers
`POST /test/run` with 500, `{"message": "tester run limit reached", "source": "tester"}`,
within the registered limit. In the stored report the test in progress is `error` with
source `tester`, and each test not yet started is `skip`, both with the message "tester
run limit reached". The tester's own `GET /test/report` returns that report; the session
cannot run again (409).

## 7. Errors

- **Project routes:** `{code, message}`. 400 `INVALID_REQUEST` (never 422); 404
  `REPOSITORY_NOT_FOUND`, `COMMIT_NOT_FOUND`, `ANALYSIS_NOT_FOUND`; 500 `ANALYSIS_FAILED`,
  `STORAGE_FAILED`.
- **Inside a saved 200 result** (`status: "ERROR"`): `CHANGE_LIMIT_EXCEEDED` (over
  2000 changed files), `MAPPING_UNSUPPORTED` (a mapped document has an unsupported
  extension; only a system with a prose detector produces it).
- **No drift verdict (Team 15 only):** not an error of the analysis. `drift_error`
  carries `MODELS_NOT_FOUND`, `INVALID_MODELS`, `PARSE_FAILED` or `FILE_TOO_LARGE`.
- **Test routes:** `{message, source}`, as the course spec defines. System
  `GET /test/report` answers 409 while preparation is in progress (course spec; v1.1
  leaves it out).

## 8. Registry and access

Both teams' "Intra-pod specification URL" links this file:
<https://github.com/MuhammadSban/DocumentationModelDrifter/blob/contract-2.4.0/docs/contract/pod-contract.md>.
Team 15's "Access / run notes" cell:

> No authentication; public GitHub repositories only. Limits: tester setup 120 s, tester
> run 600 s, system setup 90 s, 90 s per project call. One session at a time: a new
> system setup answers 409 until the last session's /test/report is read, or for 720 s
> after its setup. Spec:
> https://github.com/MuhammadSban/DocumentationModelDrifter/blob/contract-2.4.0/docs/contract/pod-contract.md

## 9. Differences from Team 16's v1.1 package, in one place

| v1.1 says | This contract says | Why |
| --- | --- | --- |
| REQ-02, section 6: every system runs the prose detector | only a system with a prose detector fills `issues` | Team 15's documentation is `/models` |
| `AnalysisResult` and its parts accept no extra fields | `drift` and `drift_error` are allowed, optional | Team 15's model check |
| no `/generate` | optional `POST /generate` | T-33 byte-for-byte check |
| system setup answers 409 for an existing session id | also 409 while another session is active (until its report is read, at most 720 s after its setup) | course spec: prevent interference between sessions |
| OpenAPI: `unmapped` holds added or modified paths | ADDED, MODIFIED, RENAMED, COPIED or TYPE_CHANGED paths | v1.1 SPEC section 6.1 and golden case c3 already say so |
| `GET /test/report` lists 400 and 404 | also 409 while preparing, and 500 (source `system`) when coverage cannot be read | course spec: 409 for reports not ready, 500 for service failures |
| `Health` has no `features` | optional `features`; absent means `["prose_detector"]`; when `/health` fails, only the tests that need a feature are `error` | a tester skips, never fails, what a system does not implement |
| acceptance criteria in SPEC section 10 | the same ten, copied word for word into section 5, plus what "doc" means for `model_drift` | the course asks the intra-pod specification to list them |
| `GET /test/report` sets no minimum length for `session_id` | at least 1 character, as `POST /test/setup` already requires | course spec: session ids are nonempty |
| no retry rule, no concurrency rule, no numbered test list | sections 2, 4 and 6 | the course asks the pod to define them |

## 10. Agreement and changes

Version 2.4.0 is proposed and pending Team 16's agreement; Team 16 has agreed to no
version yet. Every later change to any file in this folder
bumps the version and applies once
both teams agree to it. `spec-v1.1.md`, `mapping-v1.1.yaml` and `golden-outputs.json`
change only when Team 16 publishes a new version of them.
