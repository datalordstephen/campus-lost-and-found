"""FastAPI application entrypoint.

Run from the repository root:
    uv run uvicorn backend.main:app --reload
"""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend import clip_encoder, faiss_store, verification
from backend.database import init_db
from backend.routers import admin as admin_router
from backend.routers import auth as auth_router
from backend.routers import items as items_router
from backend.routers import claims as claims_router
from backend.routers import matches as matches_router

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
# Tests that never touch retrieval set this to skip the multi-second model load.
PRELOAD_MODELS = os.getenv("PRELOAD_MODELS", "1").lower() not in ("0", "false", "no")


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    init_db()
    faiss_store.init_index()
    if PRELOAD_MODELS:
        # Load once here so no request ever pays the several-second model load.
        clip_encoder.load_model()
        # Cache-only: a missing NLI checkpoint must not block startup or take
        # the API down. Retrieval still works; claim endpoints return 503.
        verification.preload_if_cached()
    yield
    # Flush the index so vectors added this session survive a restart.
    faiss_store.save_index()


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
app.include_router(items_router.router)
app.include_router(matches_router.router)
app.include_router(claims_router.router)
app.include_router(admin_router.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {
        "status": "ok",
        "clip_loaded": clip_encoder.is_loaded(),
        "nli_loaded": verification.is_loaded(),
        "faiss": faiss_store.stats(),
    }
