"""Writes the generated OpenAPI documents; CI fails if the committed copies drift (--check)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from doctracker.system.app import app as system_app
from doctracker.tester.app import app as tester_app

OUT = Path(__file__).resolve().parents[1] / "openapi"


def main() -> int:
    check = "--check" in sys.argv
    drift = False
    for name, app, server in (("system", system_app, "/system"), ("tester", tester_app, "/tester")):
        spec = app.openapi()
        spec["servers"] = [{"url": server, "description": "Relative to the deployed host"}]
        text = json.dumps(spec, indent=2, sort_keys=True) + "\n"
        path = OUT / f"{name}.openapi.json"
        if check:
            if not path.exists() or path.read_text() != text:
                print(f"{path.name} is out of date; run python scripts/export_openapi.py")
                drift = True
        else:
            OUT.mkdir(exist_ok=True)
            path.write_text(text)
            print(f"wrote {path}")
    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
