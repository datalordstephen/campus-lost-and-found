"""FastAPI application entrypoint.

Run from the repository root:
    uv run uvicorn backend.main:app --reload
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.database import init_db
from backend.routers import auth as auth_router

load_dotenv()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    init_db()
    # Phase 2 hooks in here: load the OpenCLIP model and the FAISS index once,
    # at startup, so no request ever pays that cost.
    yield


app = FastAPI(
    title="Campus Lost & Found",
    description=(
        "Zero-shot vision-language retrieval for campus lost and found item management. "
        "OpenCLIP for cross-modal matching, DistilRoBERTa NLI for ownership verification."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS or ["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Found-item photos are served straight off disk at /uploads/<hashed-name>.
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.include_router(auth_router.router)
# Phase 3: items, matches routers.  Phase 4: claims router.  Phase 5: admin.


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
