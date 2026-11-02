"""ASGI entry point hosting the system at /system and the tester at /tester."""

from __future__ import annotations

from doctracker import coverage_tracker, logging_setup

logging_setup.configure()
coverage_tracker.start()

from fastapi import FastAPI  # noqa: E402

from doctracker import __version__  # noqa: E402
from doctracker.system.app import app as system_app  # noqa: E402
from doctracker.tester.app import app as tester_app  # noqa: E402

app = FastAPI(title="Documentation Tracker (Team 16)", version=__version__)
app.mount("/system", system_app)
app.mount("/tester", tester_app)


@app.get("/")
def index() -> dict[str, str]:
    return {"system": "/system", "tester": "/tester", "system_docs": "/system/docs", "tester_docs": "/tester/docs",
            "version": __version__}
