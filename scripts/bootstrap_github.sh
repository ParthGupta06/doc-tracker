#!/usr/bin/env bash
# One-time setup: push the code repo and the deterministic fixture repo.
# Usage: scripts/bootstrap_github.sh <github-owner>
# Requires: git, python3, and either the GitHub CLI (gh, logged in) or two
# empty repos already created at github.com/<owner>/doc-tracker and
# github.com/<owner>/doc-tracker-fixtures (both PUBLIC so graders can see CI
# and the service can clone fixtures without credentials).
set -euo pipefail
OWNER="${1:?usage: scripts/bootstrap_github.sh <github-owner>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  gh repo view "$OWNER/doc-tracker" >/dev/null 2>&1 || gh repo create "$OWNER/doc-tracker" --public -d "ECE 30861 Team 16 Documentation Tracker"
  gh repo view "$OWNER/doc-tracker-fixtures" >/dev/null 2>&1 || gh repo create "$OWNER/doc-tracker-fixtures" --public -d "Pod 15/16 deterministic fixture repository"
fi

python3 "$ROOT/fixtures/build_fixture_repo.py" "$ROOT/build/fixtures" "$ROOT/build/commits.check.json" >/dev/null
diff -q "$ROOT/build/commits.check.json" "$ROOT/doctracker/tester/commits.json" \
  || { echo "Fixture SHAs differ from commits.json; do not push"; exit 1; }
( cd "$ROOT/build/fixtures" && git remote add origin "https://github.com/$OWNER/doc-tracker-fixtures.git" 2>/dev/null || true
  git push -u origin main --tags )

cd "$ROOT"
git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$OWNER/doc-tracker.git"
git push -u origin main
echo "Done. Set FIXTURE_REPO=$OWNER/doc-tracker-fixtures on Render and as a repo variable."
