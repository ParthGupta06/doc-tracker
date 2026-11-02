# Documentation Tracker: Pod 15/16 Shared Specification v1.1

Status: PROPOSED by Team 16 on 2026-10-30, pending Team 15 sign-off (see Section 11). Supersedes Phase 2 Version 1 where they differ.

## 0. How to use this package (read first if you are an AI coding agent)

1. This file is the normative source. The words MUST, MUST NOT, SHALL and SHOULD are used as in RFC 2119.
2. Field names, types, enums and status codes come from `openapi-system-v1.1.yaml`. If this file and the OpenAPI file ever disagree, the OpenAPI file wins and you MUST report the conflict instead of guessing.
3. Classification and code-to-doc links come from `mapping-v1.1.yaml`. Load that file at runtime; do not hard-code its rules.
4. `golden-outputs.json` holds the exact expected output for every fixture commit. Your implementation is correct only when it reproduces every golden case, compared by the rules in Section 9.
5. Do not invent fields, codes, finding types or categories. Do not "improve" a rule. If something is unspecified, stop and ask; record the question in Section 11.
6. No LLM or other non-deterministic component may sit in the path that produces `changes`, `skipped`, `unmapped` or `issues`.

## 1. Purpose and scope

The system helps providers of general-purpose AI models keep technical documentation current under EU AI Act Article 53(1)(a) and Annex XI. Given a public GitHub repository and a commit, it reports which files changed, classifies each change, links source files to their documentation, flags likely documentation drift as findings for human review, and saves an immutable, traceable result.

In scope: public GitHub repositories; Git commit comparison; path-based classification; explicit code-to-doc mappings; deterministic drift detection (Layer 1 for all mapped files, Layer 2 for Python sources).

Out of scope: deciding legal compliance; judging whether prose is correct; private repositories; executing repository code; editing any repository.

## 2. Glossary

| Term | Meaning |
|---|---|
| head | The commit being analyzed (`commit_id`) |
| base | The commit compared against: `base_commit`, else head's first parent, else the empty tree (root commit) |
| change | One changed path between base and head |
| mapping | An explicit `source → documentation` entry in `mapping-v1.1.yaml` |
| finding | One flagged documentation problem, always `PENDING_REVIEW` when created |
| fact | A public symbol extracted from Python source by static parsing (Section 6.3) |
| golden output | The exact expected result for a fixture commit |

## 3. Requirements

| ID | Requirement |
|---|---|
| REQ-01 | The system SHALL identify every changed path between base and head (with rename detection) and classify each path using `mapping-v1.1.yaml`, first matching rule wins. |
| REQ-02 | For every changed IMPLEMENTATION path with an explicit mapping, the system SHALL apply the detection rules in Section 6 and report each result as a Finding. |
| REQ-03 | Every new Finding SHALL have `verification_status: PENDING_REVIEW`. The system SHALL NOT approve findings or modify documentation. Review decisions are Phase 5. |
| REQ-04 | Before returning 200 from `/analyze`, the system SHALL save the full AnalysisResult as a write-once record keyed by `analysis_id`. A later run SHALL NOT overwrite it. `GET /analysis/{id}` SHALL return it unchanged. |
| REQ-05 | Invalid input, missing resources and server failures SHALL produce the errors in Section 7. A failed or incomplete check SHALL NOT be reported as SUCCESS. |
| REQ-06 | Repository content is untrusted and read-only. The system SHALL NOT execute repository code, run Git hooks, external diff or textconv drivers, or expose credentials in responses or logs. Python facts SHALL be extracted by parsing only (for example `ast.parse`), never by import or exec. |
| REQ-07 | For identical repository, head, base, `config_version` and `tool_version`, repeated runs SHALL return identical significant fields (Section 9). |

## 4. Interface summary (details in `openapi-system-v1.1.yaml`)

| Operation | Success | Errors |
|---|---|---|
| `GET /health` | 200 `{status:"ok", tool_version, config_version}` | none |
| `POST /analyze` | 200 AnalysisResult | 400 INVALID_REQUEST; 404 REPOSITORY_NOT_FOUND, COMMIT_NOT_FOUND; 500 ANALYSIS_FAILED, STORAGE_FAILED |
| `GET /analysis/{analysis_id}` | 200 saved AnalysisResult | 404 ANALYSIS_NOT_FOUND; 500 STORAGE_FAILED |
| `POST /test/setup` | 201 `{session_id}` | 400, 409, 500 with `{message, source}` |
| `GET /test/report?session_id=` | 200 `{session_id, coverage:{code}}` | 400, 404 |

Request: `{"repository": "owner/name", "commit_id": "<7-40 hex>", "base_commit": "<7-40 hex>" | null}`. Unknown request fields are ignored.

Validation failures MUST return 400 (frameworks that default to 422, such as FastAPI, MUST override this).

## 5. Analysis pipeline

1. Validate the request (400 on failure).
2. Clone the repository read-only (bare clone, hooks disabled). Missing or private repository → 404 REPOSITORY_NOT_FOUND. Timeout or Git failure → 500 ANALYSIS_FAILED.
3. Resolve head and base to full 40-character SHAs. Unknown commit → 404 COMMIT_NOT_FOUND. Root commit with no base → compare against the empty tree and return `base_commit: null`.
4. Diff base to head with rename detection (`git diff-tree -r -M --name-status`). More than `max_changed_files` (2000) → saved result with `status: ERROR`, `error.code: CHANGE_LIMIT_EXCEEDED`, empty `changes`, `skipped`, `unmapped`, `issues`.
5. Classify each path (Section 5.1). Add unsupported paths to `skipped`.
6. Run the detector (Section 6).
7. Sort `changes`, `skipped`, `unmapped`, `issues` as the OpenAPI descriptions state.
8. Save the result (write-once). Storage failure → 500 STORAGE_FAILED, and nothing is reported as success.
9. Return 200 with the result.

### 5.1 Classification

Patterns in `mapping-v1.1.yaml` are POSIX globs: `**/` matches zero or more directories, `**` matches anything, `*` matches within one path segment. Categories are tried in file order; the first match wins; no match → OTHER. Order: REQUIREMENT, SPECIFICATION, ARCHITECTURE, DESIGN, IMPLEMENTATION, DOCUMENTATION, OTHER. Because DOCUMENTATION is near the end, `docs/architecture/overview.md` is ARCHITECTURE and `docs/model.md` is DOCUMENTATION.

A path whose extension (case-insensitive) is not in `supported_extensions` and whose file name is not in `supported_filenames` still appears in `changes` and also appears in `skipped` with `reason: UNSUPPORTED_FILE_TYPE`. That is the only allowed skip reason in v1.1.

## 6. Documentation drift detector

### 6.1 Linking

A link exists only when `mappings` in `mapping-v1.1.yaml` has an entry whose `source` equals the changed path exactly. For a RENAMED change, the new path is looked up. There is no convention-based fallback in v1.1.

Every ADDED, MODIFIED, RENAMED, COPIED or TYPE_CHANGED change with category IMPLEMENTATION and no mapping entry is listed in `unmapped` and produces no finding. A DELETED unmapped path is not listed.

### 6.2 Layer 1: co-change rules (any language)

For each changed path S with category IMPLEMENTATION and mapping S → D, evaluated in this order:

| Condition at head | Finding (fact = null) |
|---|---|
| S is DELETED and D exists at head | ORPHANED_DOCUMENTATION; stop for S |
| S is DELETED and D does not exist | none; stop for S |
| D does not exist at head | MISSING_DOCUMENTATION; stop for S (Layer 2 skipped) |
| D is not among the changed paths of this diff | OUTDATED_DOCUMENTATION; continue to Layer 2 |
| D is among the changed paths | none from Layer 1; continue to Layer 2 |

If D's extension is unsupported, the analysis is a saved result with `status: ERROR` and `error.code: MAPPING_UNSUPPORTED` (HTTP 200).

### 6.3 Layer 2: fact check (Python sources only)

Runs for every non-deleted S ending in `.py` that reached Layer 2. Parse the base version of S (base version of `old_path` for a rename; empty if S is new or base is the empty tree) and the head version, with a parser only. Extract module-level public facts:

- function or async function whose name does not start with `_`: kind function, value = ordered positional plus keyword-only parameter names
- class whose name does not start with `_`: kind class
- assignment of a single literal constant to a name matching `^[A-Z][A-Z0-9_]*$`: kind constant, value = Python `repr` of the literal

"Doc mentions X" means X occurs in D's head text with no letter, digit or underscore immediately before or after it (case-sensitive). For constant values, compare against the `repr` with surrounding quotes removed.

| Fact delta | Finding if | fact |
|---|---|---|
| Name in head, not in base | doc does not mention the name → UNDOCUMENTED_SYMBOL | name |
| Function gained parameter p | doc does not mention p → STALE_SIGNATURE | `name.p` |
| Function lost parameter p | doc still mentions p → STALE_SIGNATURE | `name.p` |
| Constant value changed old → new | doc mentions old value, or does not mention new value → STALE_VALUE | name |
| Name in base, not in head | doc still mentions the name → STALE_REFERENCE | name |

Unchanged facts never produce findings.

### 6.4 Finding construction

- `finding_id` = `"fnd-"` + first 16 hex characters of SHA-256 of the UTF-8 string `"{head_commit}|{issue_type}|{code_file}|{documentation_file}|{fact or ''}"`.
- `documentation_file` is the mapped path D, even when D does not exist.
- `change_category` is IMPLEMENTATION. `verification_status` is PENDING_REVIEW.
- `explanation` is free text for humans and is never compared by tests.

### 6.5 Known limits (disclose, do not paper over)

Layer 1 proves a doc was touched, not that it is correct. Layer 2 covers only the listed Python facts. Unmapped files are invisible to the detector. Humans make the final call (REQ-03).

## 7. Errors

All project API errors use `{"code": "...", "message": "..."}` with a non-empty message. Codes: INVALID_REQUEST (400), REPOSITORY_NOT_FOUND (404), COMMIT_NOT_FOUND (404), ANALYSIS_NOT_FOUND (404), ANALYSIS_FAILED (500), STORAGE_FAILED (500). CHANGE_LIMIT_EXCEEDED and MAPPING_UNSUPPORTED appear only inside a saved 200 result's `error` field. A malformed `analysis_id` returns 404 ANALYSIS_NOT_FOUND.

Testing-interface errors use `{"message": "...", "source": "tester|system|communication|unknown"}` per the course specification.

## 8. Fixture repository

`ParthGupta06/doc-tracker-fixtures` (public). Commits are built by `fixtures/build_fixture_repo.py` with fixed author, committer and timestamps, and LF line endings, so SHAs are identical on every machine.

| Tag | SHA | Scenario |
|---|---|---|
| c0-initial | d19092e138ea3f9788a8eac76005ee53d22940da | Root commit, 11 files |
| c1-impl-only | add930c827b4f242d173fe6d26ebc068c8dd65fb | `src/model.py` changed (adds THRESHOLD), doc not updated |
| c2-add-mod-del | 332e59e3ba2b1a6c1a454ee75c3a71dfea0b4ff6 | Add unmapped `src/eval.py`, edit `docs/model.md`, delete mapped `src/train.py` |
| c3-rename | 9b03117ff9c5bfcaeb49eedfccd04aa07547ed49 | Rename `src/eval.py` → `src/evaluate.py` |
| c4-categories | 55e4b15ba4ce0a9e0923bffe1335c013b7c6ae07 | Requirement, specification, design, architecture edits |
| c5-docs-only | 807e7bbc587d8a04731a850546e6acdb175a4392 | README and docs only |
| c6-binary | 8adab1b196fab4a522459716d96f2942665b222c | Binary files changed |
| c7-code-and-doc | cb9fd8c094a53c99aec7203c12bc396f0b9bfac6 | `predict` gains `weights`; doc updated and mentions it |
| c8-missing-doc | 912b0b88a52b14c5be2accffb5c2aff92c2f59e5 | Add mapped `src/tokenizer.py`; `docs/tokenizer.md` missing |

## 9. Golden outputs and comparison rules

`golden-outputs.json` lists 10 cases (9 commits with default base, plus c3 against explicit base c0). Each case gives `request` and `expected`.

A result matches a golden case when these significant fields are equal: `head_commit`, `base_commit`, `config_version`, `status`, `error`, `changes`, `skipped`, `unmapped`, and `issues` with each finding's `explanation` removed. Fields NOT compared: `analysis_id`, `repository` casing, `tool_version`, `created_at`, `explanation`.

Expected findings at a glance:

| Case | Findings (issue_type: code_file, fact) |
|---|---|
| c0-initial | none |
| c1-impl-only | OUTDATED_DOCUMENTATION: src/model.py · UNDOCUMENTED_SYMBOL: src/model.py, THRESHOLD |
| c2-add-mod-del | ORPHANED_DOCUMENTATION: src/train.py (unmapped: src/eval.py) |
| c3-rename | none (unmapped: src/evaluate.py) |
| c4 to c6 | none |
| c7-code-and-doc | none |
| c8-missing-doc | MISSING_DOCUMENTATION: src/tokenizer.py |
| c0 to c3 explicit base | UNDOCUMENTED_SYMBOL: src/model.py, THRESHOLD · ORPHANED_DOCUMENTATION: src/train.py (unmapped: src/evaluate.py) |

## 10. Acceptance criteria and required tests

| AC | Requirement | Check | Golden / fixture |
|---|---|---|---|
| AC-01 | REQ-01 | `changes` and `skipped` equal golden | all cases |
| AC-02 | REQ-02 | Missing and outdated docs flagged | c8, c1 |
| AC-03 | REQ-02, REQ-07 | Code and doc updated together gives no finding | c7 |
| AC-04 | REQ-03 | Every finding is PENDING_REVIEW | any case with issues |
| AC-05 | REQ-03, REQ-06 | Authorized review decisions | Phase 5 |
| AC-06 | REQ-04 | Two runs give distinct ids; GET returns each unchanged, including after a restart | c2 |
| AC-07 | REQ-05 | Missing commit_id, malformed JSON, bad repository format, wrong type → 400 INVALID_REQUEST | n/a |
| AC-08 | REQ-05 | Nonexistent repo/commit → 404; unknown analysis_id → 404; mapping problem → saved ERROR | n/a |
| AC-09 | REQ-06 | Repository unchanged, no code executed, no credentials in logs | inspection, Phase 5 |
| AC-10 | REQ-07 | Five runs of c4 and of c1 give identical significant fields, including identical finding_ids | c4, c1 |

Coverage component list: C1 interface, C2 fetch and resolve, C3 diff and classify, C4 detector, C5 result builder and persistence, C6 retrieval, C7 review workflow (Phase 5).

## 11. Decision log (v1 → v1.1)

| # | Decision | Reason | Team 15 |
|---|---|---|---|
| D1 | `repository` MUST be `owner/name` | Phase 2 example omitted owner | agree / counter |
| D2 | Findings list is `issues`; Finding fields as in OpenAPI | Phase 2 prose said findings, JSON said issues | agree / counter |
| D3 | Change fields are `path`, `old_path`, `change_type`, `category` | Matches deployed Team 16 v0.3.0; Team 15 to confirm their names | agree / counter |
| D4 | Full 40-char SHAs; `base_commit: null` for root | Tests compare SHAs exactly | agree / counter |
| D5 | Missing repo or commit → 404, nothing saved; mapping problem → saved 200 ERROR | AC-08 vs Section 5.1 conflict | agree / counter |
| D6 | One shared `mapping-v1.1.yaml`; DOCUMENTATION added near lowest precedence | Phase 3 cross-test: 3 of 4 failures were category mismatches | agree / counter |
| D7 | Single skip reason UNSUPPORTED_FILE_TYPE | Phase 3 cross-test: BINARY_FILE mismatch | agree / counter |
| D8 | Error codes STORAGE_FAILED (read and write), plus the list in Section 7 | Phase 4 review found WRITE_FAILED/READ_FAILED in one reading of the spec | agree / counter |
| D9 | New `unmapped` array in AnalysisResult | Makes detector coverage visible instead of silent | agree / counter |
| D10 | Detector rules in Section 6, deterministic, no LLM in the detection path | REQ-07 repeatability, explainability, cost | agree / counter |
| D11 | `GET /health` shape in OpenAPI | Team 15 tests expected a health contract | agree / counter |
| D12 | Components C1 to C7 as the shared coverage list | Comparable component coverage | agree / counter |

Sign-off: Team 15 ______ date ______ · Team 16 ______ date ______

## 12. Agent instructions (paste into your coding agent)

```
You are implementing the Pod 15/16 Documentation Tracker system to the shared spec v1.1.
Sources of truth, in priority order: openapi-system-v1.1.yaml, SPEC.md, mapping-v1.1.yaml, golden-outputs.json.
Rules:
- Match the OpenAPI field names, types, enums and status codes exactly. Add no fields.
- Load mapping-v1.1.yaml at runtime for categories, skip rules and mappings.
- Implement Section 5 (pipeline) and Section 6 (detector) exactly as written, deterministically.
- Never execute repository code; parse Python with ast only.
- Return 400 for validation errors (override any framework default of 422).
- Write a test that runs every case in golden-outputs.json and compares significant fields per Section 9.
- Do not change a golden expectation to make a test pass. If you believe a golden value is wrong,
  stop and report it with the rule you think it violates.
- When anything is unspecified, ask instead of guessing.
```
