"""Builds the pod fixture repository with deterministic commit SHAs.

Usage: python fixtures/build_fixture_repo.py <output_dir> [manifest_path]

Every commit uses a fixed author, committer and timestamp, so running this
script anywhere produces identical SHAs. Push the result to GitHub with
`git push --mirror` (or `git push -u origin main --tags`) and the SHAs in
the manifest will match the public repository exactly.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PNG_V1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)
PNG_V2 = PNG_V1 + b"\x00\x01"

BASE_TIME = 1790000000


def run(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def write(repo: Path, rel: str, content: str | bytes) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_bytes(content.encode("utf-8"))


def commit(repo: Path, index: int, message: str, tag: str) -> str:
    stamp = f"{BASE_TIME + index * 3600} +0000"
    env = dict(os.environ)
    env.update(
        GIT_AUTHOR_NAME="Doc Tracker Fixtures",
        GIT_AUTHOR_EMAIL="fixtures@doc-tracker.invalid",
        GIT_COMMITTER_NAME="Doc Tracker Fixtures",
        GIT_COMMITTER_EMAIL="fixtures@doc-tracker.invalid",
        GIT_AUTHOR_DATE=stamp,
        GIT_COMMITTER_DATE=stamp,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
    )
    run(repo, "add", "-A", env=env)
    run(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", message, env=env)
    run(repo, "-c", "tag.gpgsign=false", "tag", tag, env=env)
    return run(repo, "rev-parse", "HEAD")


MODEL_V1 = '''"""Tiny classifier used as a documentation fixture."""


def predict(features):
    score = sum(features) / max(len(features), 1)
    return 1 if score > 0.5 else 0
'''

MODEL_V2 = '''"""Tiny classifier used as a documentation fixture."""

THRESHOLD = 0.6


def predict(features):
    score = sum(features) / max(len(features), 1)
    return 1 if score > THRESHOLD else 0
'''

MODEL_V3 = '''"""Tiny classifier used as a documentation fixture."""

THRESHOLD = 0.6


def predict(features, weights=None):
    weights = weights or [1.0] * len(features)
    score = sum(f * w for f, w in zip(features, weights)) / max(len(features), 1)
    return 1 if score > THRESHOLD else 0
'''

EVAL_PY = '''from src.model import predict


def accuracy(rows, labels):
    hits = sum(1 for r, y in zip(rows, labels) if predict(r) == y)
    return hits / max(len(labels), 1)
'''


def build(out: Path) -> dict[str, str]:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    run(out, "init", "-q", "-b", "main")
    shas: dict[str, str] = {}

    write(out, "README.md", "# Doc Tracker fixtures\n\nFixture repository for the Teams 15/16 pod.\n")
    write(out, "LICENSE", "MIT License\n")
    write(out, "src/model.py", MODEL_V1)
    write(out, "src/train.py", "def train(rows):\n    return len(rows)\n")
    write(out, "docs/model.md", "# Model\n\n`predict` returns 1 when the mean feature exceeds 0.5.\n")
    write(out, "docs/training.md", "# Training\n\n`train` counts rows.\n")
    write(out, "requirements/REQUIREMENTS.md", "# Requirements\n\n- R1: predict returns 0 or 1.\n")
    write(out, "specs/api.yaml", "openapi: 3.1.0\ninfo: {title: fixture, version: '1'}\npaths: {}\n")
    write(out, "docs/architecture/overview.md", "# Architecture\n\nSingle linear scorer.\n")
    write(out, "docs/design/decisions.md", "# Design decisions\n\n1. Mean of features.\n")
    write(out, "assets/logo.png", PNG_V1)
    shas["c0-initial"] = commit(out, 0, "Initial fixture state", "c0-initial")

    write(out, "src/model.py", MODEL_V2)
    shas["c1-impl-only"] = commit(out, 1, "Change threshold without touching docs", "c1-impl-only")

    write(out, "src/eval.py", EVAL_PY)
    write(out, "docs/model.md", "# Model\n\n`predict` returns 1 when the mean feature exceeds 0.6.\n")
    (out / "src/train.py").unlink()
    shas["c2-add-mod-del"] = commit(out, 2, "Add eval, update model doc, delete train", "c2-add-mod-del")

    run(out, "mv", "src/eval.py", "src/evaluate.py")
    shas["c3-rename"] = commit(out, 3, "Rename eval module", "c3-rename")

    write(out, "specs/api.yaml", "openapi: 3.1.0\ninfo: {title: fixture, version: '2'}\npaths: {}\n")
    write(out, "requirements/REQUIREMENTS.md", "# Requirements\n\n- R1: predict returns 0 or 1.\n- R2: weights optional.\n")
    write(out, "docs/design/decisions.md", "# Design decisions\n\n1. Mean of features.\n2. Optional weights.\n")
    write(out, "docs/architecture/overview.md", "# Architecture\n\nWeighted linear scorer.\n")
    shas["c4-categories"] = commit(out, 4, "Update spec, requirement, design and architecture", "c4-categories")

    write(out, "README.md", "# Doc Tracker fixtures\n\nFixture repository for the Teams 15/16 pod.\n\nSee docs/.\n")
    write(out, "docs/training.md", "# Training\n\nTraining was removed in c2.\n")
    shas["c5-docs-only"] = commit(out, 5, "Documentation-only change", "c5-docs-only")

    write(out, "assets/logo.png", PNG_V2)
    write(out, "data/weights.bin", bytes(range(16)))
    shas["c6-binary"] = commit(out, 6, "Binary asset changes", "c6-binary")

    write(out, "src/model.py", MODEL_V3)
    write(out, "docs/model.md", "# Model\n\n`predict(features, weights=None)` returns 1 when the weighted mean exceeds 0.6.\n")
    shas["c7-code-and-doc"] = commit(out, 7, "Weighted predict with matching doc update", "c7-code-and-doc")

    write(out, "src/tokenizer.py", "def tokenize(text):\n    return text.split()\n")
    shas["c8-missing-doc"] = commit(out, 8, "Add tokenizer without documentation", "c8-missing-doc")

    return shas


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "build/doc-tracker-fixtures")
    manifest_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    shas = build(out)
    payload = {"fixture_version": "fixtures-v1", "commits": shas}
    text = json.dumps(payload, indent=2) + "\n"
    if manifest_path:
        manifest_path.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
