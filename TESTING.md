# Testing the platform

Everything below runs from the repository root.

## 0. One-time setup

```bash
uv sync --group dev
cp .env.example .env            # then fill in SECRET_KEY and FERNET_KEY
uv run python tests/fixtures/download_fixtures.py    # 10 photos for the test suite
```

Generate the two secrets:

```bash
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

The two model checkpoints (~600 MB CLIP, ~330 MB NLI) download on first use. If a
download stalls, that is the HuggingFace `hf_xet` transfer backend — set
`HF_HUB_DISABLE_XET=1` and, ideally, a free `HF_TOKEN` from
https://huggingface.co/settings/tokens.

## 1. Automated tests

```bash
uv run pytest -m "not slow"      # ~4s   — auth, JWT, RBAC. No models loaded.
uv run pytest                    # ~2min — adds CLIP retrieval, items, claims
uv run pytest -v -s              # -s prints the retrieval and NLI score tables
```

| File | Covers |
|---|---|
| `tests/test_phase1_auth.py` | register/login/JWT, role storage, RBAC factory, 401/403/409 |
| `tests/test_phase2_retrieval.py` | embedding shape/norm, cross-modal P@1, FAISS add/search/tombstone/rebuild/persist |
| `tests/test_phase3_items.py` | upload validation, content-hash dedup, end-to-end match, encryption at rest, per-route RBAC |
| `tests/test_phase4_claims.py` | full claim journey, NLI calibration, attempt caps, score withheld from claimants |

## 2. Manual — the API

```bash
uv run uvicorn backend.main:app --reload
```

Open **http://127.0.0.1:8000/docs**. Register, copy the `access_token`, click
**Authorize**, paste it. Every endpoint is then callable from the browser.
`GET /health` reports whether both models loaded and how many vectors are indexed.

## 3. Manual — the app

Two terminals:

```bash
uv run uvicorn backend.main:app --reload     # terminal 1
cd frontend && npm run dev                   # terminal 2
```

Open **http://localhost:5173**. To populate it with realistic data instead of
clicking through an empty app:

```bash
uv run python scripts/seed_demo.py
```

That creates four accounts (password `passw0rd123` for all):

| Email | Role | For testing |
|---|---|---|
| `priya@campus.edu` | student | Handed items in; earns return credits |
| `sam@campus.edu` | student | Filed the lost reports; makes the claims |
| `otto@campus.edu` | security | Confirms custody, releases items |
| `ada@campus.edu` | admin | Stats, roles, listing removal |

### The full journey, by hand

1. **Sign in as `priya@campus.edu`** → *Hand in* → upload a photo, name a security
   post → the item is logged and you immediately see any open reports it matches.
2. **Sign in as `otto@campus.edu`** → *Incoming* → **Confirm custody** on that item
   → status goes `pending custody` → `verified`. **Find the owner** lists the open
   reports that resemble it.
3. **Sign in as `sam@campus.edu`** → *Report lost* → describe an item you know is in
   the box, and record a private detail → matches appear ranked, with the seam
   marker showing how close each is to the best.
4. Click **This is mine** → type the private detail → it is checked against your
   original report. Getting it right approves the claim; getting it wrong burns one
   of three attempts.
5. **Back as `otto@campus.edu`** → *Claims* → the approved claim shows the
   entailment score against the 70% threshold → **Release to claimant**.
6. **Sign in as `ada@campus.edu`** → the returned count goes up, and Priya now has a
   return credit.

### What to try to break

- Claim an item against **someone else's** report → 403.
- Get the private detail wrong **four times** → 429, attempts exhausted.
- Upload a `.txt` renamed to `.jpg` → 400, the bytes are checked, not the extension.
- As a student, open `/security` or `/admin` → redirected away; the API returns 403.
- Release the same claim twice → 409, and the finder is not credited twice.
- Let a token sit for 30 minutes, then act → bounced to sign-in.
- Report something that was never handed in → an empty state, not an error.

## 4. Retrieval evaluation (Phase 6)

```bash
uv run python eval/build_dataset.py --n 200    # once; downloads ~200 COCO photos
uv run python eval/evaluate.py                 # P@k, R@k, MRR at k=1,3,5
uv run python eval/evaluate.py --json eval/results.json
```

Also useful for poking at retrieval by hand, with your own photos:

```bash
uv run python scripts/try_retrieval.py "my blue water bottle" --images ~/Desktop/photos
```

## 5. Resetting

```bash
rm -f campus_lost_found.db          # accounts and items
rm -rf faiss_index/*.bin faiss_index/*.meta.json   # the vector index
rm -rf uploads/*.jpg uploads/*.png  # the photos
```

Delete all three together — a database without its index (or the reverse) leaves
items that cannot be matched.
