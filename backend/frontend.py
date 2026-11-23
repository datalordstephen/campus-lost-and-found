"""Serve the built React app from the API process, for single-container deploys.

In development Vite serves the frontend and proxies API calls to FastAPI. In a
deployment there is one origin, so FastAPI serves ``frontend/dist`` itself.

``/admin`` is both an API prefix and a client route, so paths alone cannot
decide who answers. The rule is the one the Vite proxy uses: a browser
navigation (``Accept: text/html``) gets ``index.html`` and React Router takes
over; anything else (axios, ``<img>``) goes to the API as before.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Paths that must reach FastAPI even when a browser navigates to them.
_PASSTHROUGH = ("/docs", "/redoc", "/openapi.json", "/uploads", "/assets", "/health")


def mount_frontend(app: FastAPI, dist: str | Path) -> bool:
    """Serve ``dist`` as the site root. Returns False if there is no build."""
    dist = Path(dist)
    index = dist / "index.html"
    if not index.is_file():
        return False

    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.middleware("http")
    async def spa_navigation(request: Request, call_next):
        path = request.url.path
        if (
            request.method == "GET"
            and "text/html" in request.headers.get("accept", "")
            and not path.startswith(_PASSTHROUGH)
        ):
            # A real file at the root (favicon, logo) is served as-is.
            candidate = (dist / path.lstrip("/")).resolve()
            if path != "/" and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(index)
        return await call_next(request)

    @app.get("/{filename}", include_in_schema=False)
    async def root_file(filename: str):
        # Top-level static files (favicon.svg etc.) requested without text/html.
        candidate = (dist / filename).resolve()
        if candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Not Found")

    return True
