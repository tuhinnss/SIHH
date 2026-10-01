"""Deployment entry point: the API under /api and the built frontend on one port.

Local development keeps `app.main:app` behind the Vite proxy; the Docker image runs
`uvicorn app.site:create_site --factory`.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import ROOT
from app.main import app as api, lifespan

DIST = ROOT / "frontend" / "dist"


def create_site(dist: Path = DIST) -> FastAPI:
    # a mounted app's own lifespan is never run, so the site runs the API's
    site = FastAPI(title="Kalamkaar", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    site.mount("/api", api)
    site.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return site
