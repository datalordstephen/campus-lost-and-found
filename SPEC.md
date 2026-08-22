# Campus Lost & Found — Claude Code Spec

## Project title
Development of a Zero-Shot Vision-Language Retrieval System for Campus Lost and Found Item Management

## One-line summary
A web-based lost and found platform that semantically matches lost item text descriptions to found item photographs using OpenCLIP — without domain-specific training data — verified by a DistilRoBERTa NLI model.

---

## Environment
- **OS:** macOS
- **Package manager:** uv
- **Python:** 3.10+
- **Frontend:** React + Vite
- **Backend:** FastAPI

---

## Project structure to scaffold
```
campus-lost-found/
├── backend/
│   ├── main.py                  # FastAPI app, CORS, router registration
│   ├── database.py              # SQLite engine, session, Base
│   ├── models.py                # SQLAlchemy ORM models
│   ├── schemas.py               # Pydantic request/response schemas
│   ├── auth.py                  # JWT creation, password hashing, get_current_user
│   ├── clip_encoder.py          # OpenCLIP load, encode_image(), encode_text(), encode_combined()
│   ├── faiss_store.py           # FAISS index init, add(), search(), remove(), save(), load()
│   ├── verification.py          # DistilRoBERTa NLI inference — verify_claim()
│   └── routers/
│       ├── auth.py              # POST /register, POST /login
│       ├── items.py             # POST /found, POST /lost, GET /items
│       ├── matches.py           # GET /matches/{lost_item_id}, GET /matches/found/{found_item_id}
│       └── claims.py            # POST /claim, POST /claim/verify, POST /claim/release
├── frontend/
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── api/
│       │   └── client.js        # Axios instance with JWT Authorization header
│       ├── pages/
│       │   ├── Login.jsx
│       │   ├── Register.jsx
│       │   ├── StudentDashboard.jsx
│       │   ├── SecurityDashboard.jsx
│       │   └── AdminPanel.jsx
│       └── components/
│           ├── Navbar.jsx
│           ├── ItemCard.jsx
│           ├── MatchCard.jsx
│           └── ClaimModal.jsx
├── uploads/                     # Found item photos — gitignored
├── faiss_index/                 # Persisted FAISS index — gitignored
├── pyproject.toml
├── .env
├── .gitignore
└── README.md
```

---

## Database models (SQLAlchemy)

### User
| Field | Type | Notes |
|---|---|---|
| id | Integer PK | autoincrement |
| full_name | String | |
| email | String | unique, indexed |
| hashed_password | String | bcrypt |
| role | Enum | `student` / `security` / `admin` |
| incentive_credits | Integer | default 0 |
| created_at | DateTime | default utcnow |

### FoundItem
| Field | Type | Notes |
|---|---|---|
| id | Integer PK | |
| image_path | String | hashed filename under /uploads |
| location | String | nearest security post |
| submitted_by | FK → User.id | student who found it |
| security_post_id | FK → User.id | assigned security officer |
| embedding_id | Integer | FAISS index position |
| status | Enum | `pending_custody` / `verified` / `claimed` |
| created_at | DateTime | |

### LostItem
| Field | Type | Notes |
|---|---|---|
| id | Integer PK | |
| description | String | text description |
| image_path | String | nullable — optional upload |
| private_descriptor | String | encrypted — used for NLI verification |
| location_last_seen | String | |
| reported_by | FK → User.id | |
| embedding_id | Integer | FAISS index position |
| status | Enum | `open` / `matched` / `claimed` |
| created_at | DateTime | |

### Claim
| Field | Type | Notes |
|---|---|---|
| id | Integer PK | |
| lost_item_id | FK → LostItem.id | |
| found_item_id | FK → FoundItem.id | |
| claimant_id | FK → User.id | |
| claimant_description | String | submitted text for NLI comparison |
| nli_score | Float | entailment confidence score |
| status | Enum | `pending` / `approved` / `rejected` / `released` |
| created_at | DateTime | |

### CustodyLog
| Field | Type | Type |
|---|---|---|
| id | Integer PK | |
| found_item_id | FK → FoundItem.id | |
| security_officer_id | FK → User.id | |
| action | Enum | `confirmed` / `released` |
| timestamp | DateTime | default utcnow |

---

## Core system flows

### Found item flow
1. Student uploads photo + selects nearest security post → `POST /found`
2. Backend saves image → encodes with CLIP image encoder → stores 512-dim L2-normalised embedding in FAISS → saves metadata in SQLite
3. System queries all open lost item text embeddings → returns top-5 cosine similarity matches
4. Matched students notified via in-app dashboard

### Lost item flow
1. Student submits text description + optional image + private descriptor → `POST /lost`
2. Backend encodes text (and image if provided, averaged) → stores embedding in FAISS → saves metadata + encrypted private descriptor in SQLite
3. System queries all verified found item image embeddings → returns top-5 matches displayed to student

### Claim flow
1. Student views matches → confirms item → `POST /claim` with claimant_description
2. Backend runs DistilRoBERTa NLI: compares claimant_description against stored private_descriptor
3. If entailment score > 0.7 threshold → claim status → `approved` → security officer notified
4. Security officer releases item → `POST /claim/release` → status → `released`
5. Submitting student's incentive_credits incremented by 1

---

## Key implementation details

### clip_encoder.py
```python
# Load once at startup — do NOT reload per request
model, _, preprocess = open_clip.create_model_and_transforms(
    'ViT-B-32', pretrained='laion2b_s34b_b79k'
)
tokenizer = open_clip.get_tokenizer('ViT-B-32')

# encode_image(image_path: str) -> np.ndarray  (512-dim, L2-normalised, float32)
# encode_text(text: str) -> np.ndarray
# encode_combined(text: str, image_path: str) -> np.ndarray  (average of both)
```

### faiss_store.py
```python
# IndexFlatIP — inner product on L2-normalised vectors = cosine similarity
index = faiss.IndexFlatIP(512)

# add_embedding(embedding: np.ndarray) -> int  (returns FAISS position)
# search(query_embedding: np.ndarray, k: int) -> list[dict]  [{item_id, score}]
# remove_embedding(embedding_id: int)  — mark as deleted, rebuild periodically
# save_index() / load_index()  — persist to faiss_index/index.bin
```

### verification.py
```python
# Use pretrained NLI checkpoint — no fine-tuning needed
from sentence_transformers import CrossEncoder
model = CrossEncoder('cross-encoder/nli-distilroberta-base')

# verify_claim(private_descriptor: str, claimant_description: str) -> float
# Returns entailment score (0.0 - 1.0)
# Threshold: 0.7 — approve if score >= 0.7
```

### auth.py
```python
# JWT — HS256, 30 minute expiry
# Password hashing — bcrypt via passlib
# get_current_user — FastAPI dependency, decode JWT, return User
# role_required(role: str) — dependency factory for RBAC
```

---

## API endpoints

| Method | Path | Role | Description |
|---|---|---|---|
| POST | /auth/register | public | Register new user |
| POST | /auth/login | public | Login, returns JWT |
| POST | /items/found | student | Submit found item with photo |
| POST | /items/lost | student | Report lost item |
| GET | /items/found | security/admin | List all found items |
| GET | /items/lost | student/admin | List all lost items |
| GET | /matches/{lost_item_id} | student | Get top-k matches for a lost item |
| GET | /matches/found/{found_item_id} | security | Get top-k matches for a found item |
| POST | /claims/ | student | Initiate a claim |
| POST | /claims/{id}/verify | backend | Run NLI verification |
| POST | /claims/{id}/release | security | Release item to owner |
| GET | /admin/users | admin | List all users |
| DELETE | /admin/items/{id} | admin | Remove stale listing |
| GET | /admin/stats | admin | System statistics |

---

## Environment variables (.env)
```
SECRET_KEY=your_jwt_secret_here
DATABASE_URL=sqlite:///./campus_lost_found.db
UPLOAD_DIR=./uploads
FAISS_INDEX_PATH=./faiss_index/index.bin
```

---

## Dependencies (pyproject.toml)
```toml
[project]
name = "campus-lost-found"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "python-jose[cryptography]",
    "passlib[bcrypt]",
    "python-multipart",
    "open-clip-torch",
    "faiss-cpu",
    "torch",
    "torchvision",
    "Pillow",
    "numpy",
    "sentence-transformers",
    "python-dotenv",
    "aiofiles",
]
```

---

## Build order — follow this exactly, phase by phase

### Phase 1 — Backend foundation
1. Scaffold project folders and `pyproject.toml`
2. `backend/database.py` — SQLite engine, SessionLocal, Base
3. `backend/models.py` — all 5 ORM models with correct relationships
4. `backend/schemas.py` — Pydantic schemas for all models (request + response)
5. `backend/auth.py` — bcrypt hashing, JWT create/decode, `get_current_user`, `role_required`
6. `backend/routers/auth.py` — `POST /auth/register`, `POST /auth/login`
7. `backend/main.py` — FastAPI init, CORS, create_all tables, mount auth router
8. ✅ Test: register student, security officer, admin — confirm JWT returned and role stored correctly

### Phase 2 — CLIP + FAISS
9. `backend/clip_encoder.py` — load OpenCLIP once at startup, `encode_image()`, `encode_text()`, `encode_combined()`
10. `backend/faiss_store.py` — `init_index()`, `add_embedding()`, `search()`, `save_index()`, `load_index()`
11. ✅ Test: encode a sample image and a matching text description — confirm cosine similarity score is high

### Phase 3 — Item endpoints
12. `backend/routers/items.py` — `POST /found` (upload image, encode, store), `POST /lost` (text/image/both, encode, store)
13. `backend/routers/matches.py` — `GET /matches/{lost_item_id}`, `GET /matches/found/{found_item_id}`
14. ✅ Test: submit a found item photo, submit a matching lost item description, confirm top-k returns the correct match

### Phase 4 — Verification + claims
15. `backend/verification.py` — load `cross-encoder/nli-distilroberta-base`, `verify_claim(private_descriptor, claimant_description) -> float`
16. `backend/routers/claims.py` — full claim flow: initiate → NLI verify → security release → incentive credit
17. ✅ Test: full end-to-end — match found → claim initiated → NLI passes → security releases → incentive credited

### Phase 5 — Frontend
18. Scaffold React + Vite frontend, configure Axios client with JWT header
19. `Login.jsx` and `Register.jsx`
20. `StudentDashboard.jsx` — report lost item, submit found item, view matches, claim flow
21. `SecurityDashboard.jsx` — confirm custody, view claim requests, release items
22. `AdminPanel.jsx` — user management, stale listing removal, stats
23. ✅ Test: full user journey for all three roles in browser

### Phase 6 — Evaluation
24. Build `eval/evaluate.py` — loads 150-200 image-description test pairs, runs retrieval, computes P@k, R@k, MRR at k=1,3,5
25. Build `eval/baseline.py` — TF-IDF keyword baseline for comparison
26. ✅ Test: confirm CLIP retrieval outperforms TF-IDF baseline on test set

---

## Frontend design guidelines (apply from Phase 5 onwards)

### Styling
- Use **Tailwind CSS** — install via the Vite plugin (`@tailwindcss/vite`)
- **Color system:**
  - Background: `slate-950` (#0a0f1e) — deep dark navy
  - Surface/cards: `slate-900` (#0f172a)
  - Border: `slate-800`
  - Primary accent: `teal-500` (#14b8a6) — buttons, highlights, active states
  - Text primary: `slate-100`
  - Text secondary: `slate-400`
- **Typography:** Inter font (import from Google Fonts in index.html)
- **Icons:** `lucide-react` — use consistently across all pages
- **No default browser styles** — Tailwind's preflight handles this

### Layout
- Every authenticated page: left sidebar nav + main content area
- Sidebar width: fixed `w-56`, full height, `slate-900` background
- Main content: scrollable, padded `p-6`, max-width `max-w-5xl mx-auto`
- Cards: `rounded-xl border border-slate-800 bg-slate-900 p-4 shadow-sm`
- Buttons: primary = `bg-teal-500 hover:bg-teal-400 text-white rounded-lg px-4 py-2`

### Components — build these first before any page
- `Navbar.jsx` — sidebar with role-aware nav links and logout
- `ItemCard.jsx` — displays a found or lost item (image, description, status badge, timestamp)
- `MatchCard.jsx` — displays a match result with similarity score and claim button
- `ClaimModal.jsx` — modal overlay for submitting claimant description

### UX rules
- All interactive elements have hover + focus transitions (`transition-all duration-150`)
- Loading states on every async action (spinner or skeleton)
- Empty states for all lists ("No lost items reported yet")
- Toast notifications for success/error actions (use a simple custom toast, no heavy library)
- Mobile-first — all layouts must work on 375px screen width

### npm packages to install at Phase 5 start
```bash
npm install axios react-router-dom lucide-react
npm install -D tailwindcss @tailwindcss/vite
```

### Tailwind config note
With Vite + Tailwind v4, add to `vite.config.js`:
```js
import tailwindcss from '@tailwindcss/vite'
export default { plugins: [tailwindcss()] }
```
And in `src/index.css`:
```css
@import "tailwindcss";
```

### Design system file
Before building any page, create `src/theme.js`:
```js
export const theme = {
  card: "rounded-xl border border-slate-800 bg-slate-900 p-4 shadow-sm",
  button: {
    primary: "bg-teal-500 hover:bg-teal-400 text-white rounded-lg px-4 py-2 transition-all duration-150 font-medium",
    secondary: "border border-slate-700 text-slate-300 hover:bg-slate-800 rounded-lg px-4 py-2 transition-all duration-150",
    danger: "bg-red-500 hover:bg-red-400 text-white rounded-lg px-4 py-2 transition-all duration-150",
  },
  input: "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-teal-500",
  badge: {
    open: "bg-teal-500/10 text-teal-400 text-xs px-2 py-0.5 rounded-full",
    pending: "bg-amber-500/10 text-amber-400 text-xs px-2 py-0.5 rounded-full",
    claimed: "bg-slate-700 text-slate-400 text-xs px-2 py-0.5 rounded-full",
  }
}
```
Every component imports from this file — never hardcode class strings.

---

## First message to paste into Claude Code
> Read SPEC.md fully before writing any code. Then begin Phase 1: scaffold the project structure, create pyproject.toml with uv, and build database.py, models.py, schemas.py, auth.py, routers/auth.py, and main.py in that order. After each file, tell me what was built and what to run to test it before moving to the next file.
