# Phase 4 mapping investigation

Baseline: Phase 2 sections 3.1, 4.1, 6.2 and Risk 1. The implemented rule is a
warning heuristic based on explicit paths and file co-change. No confidence score
is included. These are Team 16 implementation/test observations, not newly approved
pod expectations or a claim that semantic correctness is solved.

| Fixture | Label / expected behavior | Automated observation |
|---|---|---|
| c1-impl-only | Changed model, unchanged document | One OUTDATED_DOCUMENTATION finding |
| c8-missing-doc | Added tokenizer, expected document absent | One MISSING_DOCUMENTATION finding |
| c7-code-and-doc | Correct source/document update | No warning |
| c5-docs-only | Documentation-only update | No warning |
| c9-incorrect-doc | Source threshold 0.8, edited document still says 0.6 | No warning: known semantic false negative |
| c10-unreadable-doc | Changed mapped markdown contains binary bytes | Saved ERROR / CHECKS_SKIPPED / FILE_UNREADABLE |

`fixtures/build_fixture_repo.py` generates reproducible commits; hashes are in
`doctracker/tester/commits.json`. Existing c0-c8 hashes are unchanged. The added c9/c10
commits are local reproducible fixtures until separately published; the network
suite uses only the original public c0-c8 inputs. `tests/test_detection.py` checks
exact finding fields, IDs across five runs, pending state, original evidence,
invalid mappings, unsupported mapped types, unreadable docs and the false-negative
investigation. It does not turn the incorrect-document example into proof of
correctness. The document edit really remains wrong even though the heuristic
completes successfully.

## Decision still required from the pod

Agree whether to retain the explicitly limited co-change warning scope or define
selected fact comparisons with shared oracles. A content comparison would need
specified supported facts, parsers and error behavior; adding an ad-hoc detector
for one threshold would overstate general coverage. No approval or scope reduction
is claimed here. Keep the risk open, demonstrate the counterexample, and obtain
both teams' recorded decision (and instructor approval if shared scope changes).

## Review checklist

- Check fixture labels independently of the implementation.
- Confirm Version 1 field names, rename representation and error codes on both teams.
- Review exact mappings and the policy for deletion/renaming and unsupported files.
- Run both cross-team directions after deployment and retain report/session IDs.
- Keep human decisions separate from immutable PENDING_REVIEW findings.
