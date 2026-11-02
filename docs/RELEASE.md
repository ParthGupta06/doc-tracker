# Phase 4 release and evidence checklist

This branch contains v0.4.0 code. It is not a declaration that production is updated.

1. Review the pull request, especially the Version 1 compatibility corrections in
   SYSTEM.md. Run CI and require lint, type, dependency, schema and unit/API checks.
2. Publish the reviewed commit through the existing team release process. Render's
   checked-in configuration has `autoDeploy: false`; merging alone is insufficient.
   The tag workflow can use RENDER_DEPLOY_HOOK if that secret is configured.
3. Confirm `/system/health` and `/tester/health` report 0.4.0. Verify the deployed SHA
   in Render. A health version alone does not identify the exact commit.
4. Run `scripts/run_suite.py` against the deployed system. T-01 to T-21 should
   execute; T-22/T-23 remain explicitly skipped. Preserve the JSON report.
5. Run the updated tester against Team 15 and obtain their fresh run against Team 16.
   Record schema mismatches honestly. Version 1.1 proposal approval is not assumed.
6. Update registry/run notes and the submission with exact deployed tag/SHA, report
   counts, links, limits and pending pod decisions. Do not substitute local results
   for a deployed run or the other team's test results.

## Durable evidence (Phase 5 integration; existing backend)

The free Render local filesystem is not durable across instance replacement.
Use the team's dedicated evidence repository with EVIDENCE_REPO/EVIDENCE_TOKEN and
optionally EVIDENCE_BRANCH, configured through deployment secrets. Use a token
restricted to that repository; never put it in chat or source. Enabling this
requires the deployment owner and appropriate authorization. The repository is a
separate evidence destination, not the analyzed source repository.

Demonstrate AC-06 by running two identical analyses, saving both responses and IDs,
restarting the deployed service, then retrieving both and comparing exact JSON.
Retain the restart evidence. A same-process retrieve or a local test does not prove
that the hosted service is durable. Authorized review records remain Phase 5.
