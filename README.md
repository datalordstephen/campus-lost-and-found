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

Two processes. Always launch the backend from the repository root — the paths in
`.env` are relative to it.

```bash
uv run uvicorn backend.main:app --reload    # terminal 1
cd frontend && npm run dev                  # terminal 2
```

- App: http://localhost:5173
- API: http://127.0.0.1:8000
- Interactive docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health — reports whether CLIP and NLI are loaded

Vite proxies `/auth`, `/items`, `/matches`, `/claims`, `/admin` and `/uploads` to the
backend, so the browser makes same-origin calls and no CORS preflight is involved in dev.

> Use **localhost**, not `127.0.0.1`, for the frontend — Vite binds to `::1` only, so
> `http://127.0.0.1:5173` will refuse the connection while `http://localhost:5173` works.

See **[TESTING.md](TESTING.md)** for the full manual and automated test guide.

## Test

```bash
uv run pytest -v                    # everything
uv run pytest -m "not slow" -v      # skip tests that load model checkpoints
```

Phase 2's retrieval test scores real photographs. Fetch them once (they are gitignored):

```bash
uv run python tests/fixtures/download_fixtures.py
```

## Build phases

| Phase | Scope | Status |
|---|---|---|
| 1 | Backend foundation — DB, models, schemas, auth, `/auth` router, app | ✅ |
| 2 | CLIP encoder + FAISS store | ✅ P@1 = 10/10 zero-shot on held-out photos |
| 3 | Item + match endpoints | ✅ P@1 = 8/10 on natural student phrasing |
| 4 | NLI verification + claim flow | ✅ 0 false approvals across all impostor cases |
| 5 | React frontend | ✅ all three role journeys pass end to end |
| 6 | Retrieval evaluation vs. TF-IDF baseline | ✅ R@1 0.625 vs 0.315 (p<0.0001) |

## Layout

```
backend/
  database.py      SQLite engine, SessionLocal, Base, get_db
  models.py        User, FoundItem, LostItem, Claim, CustodyLog
  schemas.py       Pydantic request/response models
  auth.py          bcrypt, JWT, get_current_user, role_required, field encryption
  clip_encoder.py  OpenCLIP load + encode_image/encode_text/encode_combined
  faiss_store.py   two IndexFlatIP indexes ("found" / "lost"), soft delete, persistence
  verification.py  DistilRoBERTa NLI — verify_claim(premise, hypothesis) -> entailment
  routers/
    auth.py        POST /auth/register, POST /auth/login, GET /auth/me
    items.py       POST/GET /items/found, POST/GET /items/lost
    matches.py     GET /matches/{lost_id}, GET /matches/found/{found_id}
    claims.py      POST /claims/, /claims/{id}/verify, /claims/{id}/release
    admin.py       /admin/users, /admin/stats, /admin/items/*, /admin/index/rebuild
frontend/          React + Vite + Tailwind v4
  src/theme.js     design system — every component imports from here
  src/auth.jsx     session context (JWT in localStorage, revalidated on boot)
  src/api/client.js  axios instance, JWT header, 401 -> /login
  src/components/  Navbar, ItemCard, MatchCard, ClaimModal, Toast, Spinner
  src/pages/       Login, Register, StudentDashboard, SecurityDashboard, AdminPanel
eval/              build_dataset.py, evaluate.py, baseline.py, metrics.py
scripts/           seed_demo.py, try_retrieval.py
tests/             pytest checkpoints, one per phase
uploads/           found-item photos (gitignored)
faiss_index/       persisted FAISS index (gitignored)
```

## Evaluation results

200 image/caption pairs sampled from COCO val2017, restricted to object categories
that plausibly turn up in a lost-and-found box, capped per category. Each image
contributes two independent human captions: one is the lost report (the query),
the other is the finder's own description (what the keyword baseline searches).
Neither was written with this system in mind.

| method | R@1 | R@3 | R@5 | MRR | median rank |
|---|---|---|---|---|---|
| **CLIP** (report → photograph) | **0.625** | **0.865** | **0.950** | **0.757** | **1** |
| CLIP + `"a photo of"` template | 0.630 | 0.860 | 0.925 | 0.757 | 1 |
| CLIP (report → photo + finder's text) | 0.630 | 0.815 | 0.885 | 0.736 | 1 |
| TF-IDF baseline (report → finder's text) | 0.315 | 0.455 | 0.605 | 0.439 | 4 |

CLIP beats the keyword baseline by **+31 points at R@1** and **+34 points at R@5**
(paired bootstrap over queries, p < 0.0001), with no campus training data at all.
95% CI on CLIP R@1 is [0.560, 0.695]; on TF-IDF, [0.250, 0.380] — the intervals do
not overlap.

Two hypotheses did **not** survive contact with the data:

- **Prompt templating does not help.** Phase 3 suggested prefixing descriptions with
  `"a photo of"` would recover accuracy lost to conversational phrasing. It moves R@1
  by +0.005 (inside the noise) and *costs* 2.5 points at R@5. Reported as a negative
  result rather than quietly adopted.
- **Averaging the photo with the finder's description hurts.** It matches at R@1 but
  loses 5 points at R@3 and 6.5 at R@5, because a weak or generic finder description
  drags the vector away from the image. `encode_combined` is still what
  `items.py` indexes when a description is supplied; worth revisiting.

Failures are dominated by captions that do not describe the target object at all
(`"There is a person in the picture by itself."` for a kite photo) — a property of
COCO captions, not of the retrieval.

Reproduce:

```bash
uv run python eval/build_dataset.py --n 200
uv run python eval/evaluate.py --json eval/results.json
```

## Retrieval notes

- **Two FAISS indexes, not one.** A lost report is only ever scored against found-item photos
  and vice versa, so the store keeps separate `found.bin` and `lost.bin` in the directory
  `FAISS_INDEX_PATH` points at. One shared index would mean over-fetching and discarding half
  the neighbours, with no `k` that guarantees enough survivors.
- **Deletes are tombstones.** `IndexFlatIP.remove_ids` renumbers every vector after the removed
  one, which would silently invalidate every `embedding_id` already in SQLite. `remove_embedding`
  marks the position dead and search filters it out; `rebuild()` does the real compaction and
  returns an old→new position map to apply to the DB in the same transaction.
- **Score scale.** Raw CLIP cosine similarity for a *correct* image/text pair lands around
  **0.22–0.33**, not near 1.0 (measured: correct mean 0.28, incorrect mean 0.13). Do not surface
  the raw number to students as a percentage in Phase 5 — it reads as a broken match. Rank, or
  rescale for display.
- **CPU by default.** `CLIP_DEVICE=mps` is faster but its reductions are not bit-reproducible,
  which would make the Phase 6 evaluation numbers move between runs.
- **Prompt phrasing costs accuracy.** The same 10 photos score P@1 = 10/10 against clean
  `"a photo of a bicycle"` prompts but **8/10** against realistic student phrasing
  (`"my bicycle taken from the rack outside"`). Prompt templating — prefixing the stored
  description with `"a photo of"` before encoding — is the standard zero-shot fix and is worth
  measuring as a variable in Phase 6 rather than assuming.
- **Match strength is shown as a rank-relative share, not raw cosine.** `MatchCard` runs a
  softmax over the returned candidates; the raw cosine is still displayed in small monospace
  because the evaluation needs it.
- **macOS OpenMP.** faiss-cpu and torch each bundle an OpenMP runtime; constructing a torch
  model off the main thread with both loaded segfaults. `tests/conftest.py` sets
  `KMP_DUPLICATE_LIB_OK` / `OMP_NUM_THREADS=1`. Production is unaffected — uvicorn runs
  lifespan on the main thread.

## Verification notes

- **Direction matters.** The stored private descriptor is the NLI *premise*, the claimant's text
  is the *hypothesis*: "given what the owner recorded, does the claimant's statement follow?"
  This is asymmetric — a vague claim is entailed by a specific premise more easily than the
  reverse, so saying little is treated generously. `verify_claim_symmetric` takes the minimum of
  both directions and is the stricter rule; it is exposed but not wired in, so Phase 6 can
  compare the two on the same data.
- **The label index is read off the checkpoint**, not hardcoded — NLI models disagree about
  which logit is entailment.
- **No impostor claim was approved** in any tested case — wrong colour, wrong item, vague guess
  and direct contradiction all score 0.000-0.004 entailment. The security-critical direction holds.
- **But the model has two measured weaknesses**, pinned by tests so a scoring change is a
  deliberate decision rather than silent drift:
  - *False negatives on verbose true claims.* A real owner who adds detail the record does not
    contain gets neutral, not entailment. "the handle is scratched and **I stuck** a blue sticker
    under the canopy" scores **0.167** and is rejected, because who placed the sticker was never
    recorded. See `test_verbose_true_claims_are_false_negatives`.
  - *Partial guesses pass.* "the handle has a scratch" scores **0.962** without the claimant
    knowing about the sticker at all — forward entailment cannot express "you must know
    everything we recorded". See `test_partial_guesses_currently_pass`.
  - A clause-coverage rule was prototyped as a fix and scored no better (5/7 vs 5/7) with a naive
    splitter, so it is **not** recommended without further work. This is a genuine open problem
    worth reporting rather than hiding.

## Security notes

- `LostItem.private_descriptor` is encrypted at rest with Fernet (`FERNET_KEY`) and is never
  serialised into any response model. It is decrypted only as the NLI premise at claim time.
- Uploads are stored under a **sha256 content hash**, never the client-supplied filename — no
  path traversal, and re-uploading identical bytes reuses one file.
- **Claimants never see `nli_score`.** Returning the entailment probability to whoever wrote the
  text turns verification into a hill-climbing game: tweak the wording, watch the number move,
  repeat until it clears 0.7. Claimants get a verdict (`ClaimReceipt`); staff get the score
  (`ClaimOut`). Attempts are also capped at `MAX_CLAIM_ATTEMPTS` (default 3) per user per item.
  Neither safeguard is in the spec — both close a real hole in the ownership check.
- `POST /auth/register` currently honours the `role` field from the request body so all three
  account types can be provisioned without a seeding script. A public deployment should force
  `student` there and promote staff through the admin panel instead.
