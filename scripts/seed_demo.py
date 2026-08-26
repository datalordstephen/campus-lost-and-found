"""Populate a running instance with realistic demo data.

Start both servers first, then:

    uv run python scripts/seed_demo.py

Creates four accounts (password `passw0rd123` for all), hands in six items,
files two lost reports, and leaves one approved and one rejected claim at the
security desk so every state in the UI has something in it.

Safe to re-run: existing accounts are logged into rather than recreated, and
uploads are content-hashed so photos are not duplicated on disk.
"""
import json, os, sys, urllib.error, urllib.request
from pathlib import Path

BASE = os.getenv("CLF_BASE_URL", "http://localhost:5173")  # the Vite proxy; use :8000 for the API direct
FIX = Path("tests/fixtures/images")

def req(method, path, token=None, body=None, fields=None, files=None):
    headers = {}
    if token: headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode(); headers["Content-Type"] = "application/json"
    elif fields or files:
        b = "----seed"
        parts = []
        for k, v in (fields or {}).items():
            parts.append(f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
        for k, (n, blob, ct) in (files or {}).items():
            parts.append(f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{n}\"\r\nContent-Type: {ct}\r\n\r\n".encode() + blob + b"\r\n")
        parts.append(f"--{b}--\r\n".encode())
        data = b"".join(parts); headers["Content-Type"] = f"multipart/form-data; boundary={b}"
    r = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=180) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try: return e.code, json.loads(raw or b"null")
        except Exception: return e.code, raw.decode()[:200]

def account(name, email, role):
    st, b = req("POST", "/auth/register", body={"full_name": name, "email": email, "password": "passw0rd123", "role": role})
    if st == 409:
        st, b = req("POST", "/auth/login", body={"email": email, "password": "passw0rd123"})
    return b["access_token"], b["user"]["id"]

FIN, FIN_ID = account("Priya Raman", "priya@campus.edu", "student")
OWN, OWN_ID = account("Sam Oyelaran", "sam@campus.edu", "student")
OFF, OFF_ID = account("Otto Mensah", "otto@campus.edu", "security")
ADM, ADM_ID = account("Ada Nkemdirim", "ada@campus.edu", "admin")
print("accounts ready")

# A shelf of handed-in property.
SHELF = [
    ("umbrella",     "Black umbrella, wooden handle", "Main Gate Security Post"),
    ("backpack",     "Grey backpack, trekking straps", "Sports Centre Post"),
    ("water_bottle", "Steel water bottle",            "Main Gate Security Post"),
    ("headphones",   "Over-ear headphones",           "Library Post"),
    ("keys",         "Keys on a red keyring",         "Main Gate Security Post"),
    ("laptop",       "Silver laptop",                 "Library Post"),
]
found = {}
for slug, desc, loc in SHELF:
    p = FIX / f"{slug}.jpg"
    if not p.exists(): continue
    st, b = req("POST", "/items/found", FIN, fields={"location": loc, "description": desc},
                files={"image": (f"{slug}.jpg", p.read_bytes(), "image/jpeg")})
    if st == 201:
        found[slug] = b["item"]["id"]
        print(f"  logged {slug} -> F-{b['item']['id']:03d}")

# Custody confirmed on most, one left pending so both stamps show.
for slug, fid in list(found.items())[:-1]:
    req("POST", f"/items/found/{fid}/confirm-custody", OFF)

# Open reports from a second student.
REPORTS = [
    ("an umbrella I left by the library entrance", "Library entrance",
     "there is a deep scratch across the handle and a blue sticker under the canopy"),
    ("my steel water bottle, dented near the base", "Sports Centre",
     "the lid has a hairline crack and my initials are on the base"),
]
lost = []
for desc, place, secret in REPORTS:
    st, b = req("POST", "/items/lost", OWN,
                fields={"description": desc, "location_last_seen": place, "private_descriptor": secret})
    if st == 201:
        lost.append(b["item"]["id"])
        top = b["matches"][0] if b["matches"] else None
        print(f"  report R-{b['item']['id']:03d} -> top {('F-%03d @ %.3f' % (top['item']['id'], top['score'])) if top else 'none'}")

# One approved claim waiting at the desk, one rejected, so the queue has both.
if lost and "umbrella" in found:
    req("POST", "/claims/", OWN, body={"lost_item_id": lost[0], "found_item_id": found["umbrella"],
        "claimant_description": "it's got a scratch on the handle and there's a blue sticker underneath"})
if len(lost) > 1 and "water_bottle" in found:
    req("POST", "/claims/", OWN, body={"lost_item_id": lost[1], "found_item_id": found["water_bottle"],
        "claimant_description": "it is plain and unmarked, no cracks anywhere"})

st, claims = req("GET", "/claims/", OFF)
if st == 200:
    for c in claims:
        print(f"  claim {c['id']}: {c['status']} (entailment {c['nli_score']:.3f})")

print("\nSign in at", BASE, "— password 'passw0rd123' for all:")
for email, role in [("priya@campus.edu", "student, handed items in"),
                    ("sam@campus.edu", "student, filed the reports"),
                    ("otto@campus.edu", "security"),
                    ("ada@campus.edu", "admin")]:
    print(f"  {email:<20} {role}")
