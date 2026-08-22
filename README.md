# Campus Lost & Found

Development of a Zero-Shot Vision-Language Retrieval System for Campus Lost and Found Item Management.

A web platform that semantically matches lost-item **text descriptions** to found-item **photographs** using OpenCLIP — with no domain-specific training data — and verifies ownership claims with a DistilRoBERTa NLI cross-encoder.

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + SQLAlchemy 2.0 + SQLite |
| Retrieval | OpenCLIP `ViT-B-32` (`laion2b_s34b_b79k`), 512-dim, L2-normalised |
| Vector index | FAISS `IndexFlatIP` (inner product on unit vectors = cosine similarity) |
| Verification | `cross-encoder/nli-distilroberta-base`, entailment threshold 0.7 |
| Auth | JWT (HS256, 30 min) + bcrypt |
| Frontend | React + Vite + Tailwind CSS v4 |

## Setup

```bash
uv sync --group dev          # creates .venv on Python 3.11
cp .env.example .env         # then fill in SECRET_KEY and FERNET_KEY
```

Generate the two secrets:

```bash
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Run

Always launch from the repository root — the paths in `.env` are relative to it.

```bash
uv run uvicorn backend.main:app --reload
```

- API: http://127.0.0.1:8000
- Interactive docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

## Test

```bash
uv run pytest -v
```

## Build phases

| Phase | Scope | Status |
|---|---|---|
| 1 | Backend foundation — DB, models, schemas, auth, `/auth` router, app | ✅ |
| 2 | CLIP encoder + FAISS store | ⬜ |
| 3 | Item + match endpoints | ⬜ |
| 4 | NLI verification + claim flow | ⬜ |
| 5 | React frontend | ⬜ |
| 6 | Retrieval evaluation vs. TF-IDF baseline | ⬜ |

## Layout

```
backend/
  database.py      SQLite engine, SessionLocal, Base, get_db
  models.py        User, FoundItem, LostItem, Claim, CustodyLog
  schemas.py       Pydantic request/response models
  auth.py          bcrypt, JWT, get_current_user, role_required, field encryption
  clip_encoder.py  (Phase 2)
  faiss_store.py   (Phase 2)
  verification.py  (Phase 4)
  routers/
    auth.py        POST /auth/register, POST /auth/login, GET /auth/me
tests/             pytest checkpoints, one per phase
uploads/           found-item photos (gitignored)
faiss_index/       persisted FAISS index (gitignored)
```

## Security notes

- `LostItem.private_descriptor` is encrypted at rest with Fernet (`FERNET_KEY`) and is never
  serialised into any response model. It is decrypted only as the NLI premise at claim time.
- `POST /auth/register` currently honours the `role` field from the request body so all three
  account types can be provisioned without a seeding script. A public deployment should force
  `student` there and promote staff through the admin panel instead.
