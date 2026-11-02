"""ASGI entry point hosting the system at /system and the tester at /tester."""

from __future__ import annotations

from pathlib import Path

from doctracker import coverage_tracker, logging_setup

logging_setup.configure()
coverage_tracker.start()

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from doctracker import __version__  # noqa: E402
from doctracker.system.app import app as system_app  # noqa: E402
from doctracker.tester.app import app as tester_app  # noqa: E402

app = FastAPI(title="Documentation Tracker (Team 16)", version=__version__)
WEB = Path(__file__).resolve().parent / "web"


@app.get("/system", include_in_schema=False)
@app.get("/system/", include_in_schema=False)
def system_home() -> RedirectResponse:
    return RedirectResponse("/system/docs")


@app.get("/tester", include_in_schema=False)
@app.get("/tester/", include_in_schema=False)
def tester_home() -> RedirectResponse:
    return RedirectResponse("/tester/docs")


app.mount("/system", system_app)
app.mount("/tester", tester_app)
app.mount("/assets", StaticFiles(directory=WEB), name="assets")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/info")
def info() -> dict[str, str]:
    return {"system": "/system", "tester": "/tester", "system_docs": "/system/docs", "tester_docs": "/tester/docs",
            "version": __version__}
