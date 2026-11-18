"""Get a machine demo-ready, and prove it is before anyone is watching.

    uv run python scripts/demo.py reset    # servers DOWN: wipe to a clean slate
    uv run python scripts/demo.py check    # servers UP: pre-flight everything

The two things that go wrong in a live demo are stale state and the model load.
CLIP (~600 MB) and the NLI cross-encoder (~330 MB) are loaded at startup, but
the first *retrieval* still pays for warming caches, so `check` runs a real
query to absorb that before your supervisor is looking at the screen.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(os.getenv("CLF_ROOT", Path(__file__).resolve().parent.parent))
API = os.getenv("CLF_API_URL", "http://localhost:8000")
APP = os.getenv("CLF_BASE_URL", "http://localhost:5173")


def _state_paths() -> tuple[Path, Path, Path]:
    """Where the app keeps its state, read from the same .env the app reads."""
    for line in (ROOT / ".env").read_text().splitlines() if (ROOT / ".env").exists() else []:
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

    db = os.getenv("DATABASE_URL", "sqlite:///./campus_lost_found.db")
    db_path = ROOT / db.replace("sqlite:///", "").lstrip("./") if db.startswith("sqlite") else None
    index_dir = ROOT / Path(os.getenv("FAISS_INDEX_PATH", "./faiss_index/index.bin")).parent
    uploads = ROOT / Path(os.getenv("UPLOAD_DIR", "./uploads"))
    return db_path, index_dir, uploads

OK, BAD, WARN = "  ok   ", "  FAIL ", "  warn "


def port_open(host: str, port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(1.5)
        try:
            # localhost may resolve to ::1 first; try every family.
            for family, _, _, _, addr in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
                with socket.socket(family) as probe:
                    probe.settimeout(1.5)
                    if probe.connect_ex(addr) == 0:
                        return True
        except OSError:
            pass
    return False


def get(url: str, token: str | None = None, timeout: int = 120):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read() or b"null")


def post(url: str, body: dict, timeout: int = 120):
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read() or b"null")


# --------------------------------------------------------------------------- #
def reset() -> int:
    """Wipe to a clean slate. Must run with the API stopped.

    The FAISS index lives in memory while the app runs and is flushed on
    shutdown, so deleting the files underneath a running server just gets them
    written back out again.
    """
    api = urllib.parse.urlparse(API)
    api_port = api.port or 8000
    if port_open(api.hostname or "localhost", api_port):
        print(f"The API is still running on :{api_port}.")
        print("Stop it first — otherwise it will write its in-memory index back out.")
        return 1

    db_path, index_dir, upload_dir = _state_paths()

    targets = [db_path] if db_path else []
    targets += sorted(index_dir.glob("*.bin")) + sorted(index_dir.glob("*.json"))
    uploads = [p for p in upload_dir.glob("*") if p.name != ".gitkeep"] if upload_dir.exists() else []

    for path in targets:
        if path.exists():
            path.unlink()
            print(f"  removed {path.relative_to(ROOT)}")

    if uploads:
        keep = ROOT / "test-imgs"
        keep.mkdir(exist_ok=True)
        for path in uploads:
            # Photos are content-hashed, so this is a copy-if-absent, not a move
            # that could lose something.
            if not (keep / path.name).exists():
                shutil.copy2(path, keep / path.name)
            path.unlink()
        print(f"  cleared {len(uploads)} uploads (copies kept in test-imgs/)")

    print("\nClean. Now start both servers, then: uv run python scripts/seed_demo.py")
    return 0


# --------------------------------------------------------------------------- #
def check() -> int:
    """Pre-flight. Everything a demo needs, verified end to end."""
    failures = 0

    print("Servers")
    api = urllib.parse.urlparse(API)
    app = urllib.parse.urlparse(APP)
    api_up = port_open(api.hostname or "localhost", api.port or 8000)
    app_up = port_open(app.hostname or "localhost", app.port or 5173)
    print(f"{OK if api_up else BAD}API   {api.netloc}")
    print(f"{OK if app_up else BAD}app   {app.netloc}")
    if not (api_up and app_up):
        print("\nStart them:")
        print("  uv run uvicorn backend.main:app --reload")
        print("  cd frontend && npm run dev")
        return 1

    print("\nModels")
    try:
        health = get(f"{API}/health", timeout=300)
    except Exception as exc:
        print(f"{BAD}/health unreachable: {exc}")
        return 1
    clip, nli = health.get("clip_loaded"), health.get("nli_loaded")
    print(f"{OK if clip else BAD}CLIP loaded")
    print(f"{OK if nli else BAD}NLI loaded")
    failures += (not clip) + (not nli)
    if not nli:
        print("       claim verification will 503 — fetch the checkpoint:")
        print("       HF_HUB_DISABLE_XET=1 uv run huggingface-cli download "
              "cross-encoder/nli-distilroberta-base")

    print("\nProxy")
    try:
        get(f"{APP}/health", timeout=60)
        print(f"{OK}app -> API via the Vite proxy")
    except Exception as exc:
        print(f"{BAD}the app cannot reach the API: {exc}")
        failures += 1

    print("\nData")
    try:
        session = post(f"{APP}/auth/login",
                       {"email": "sam@campus.edu", "password": "passw0rd123"})
        token = session["access_token"]
    except urllib.error.HTTPError:
        print(f"{BAD}demo accounts missing — run: uv run python scripts/seed_demo.py")
        return 1

    reports = get(f"{APP}/items/lost?mine=true", token)
    index = health.get("faiss", {})
    found_n = index.get("found", {}).get("live", 0)
    print(f"{OK if found_n else BAD}{found_n} found items indexed")
    print(f"{OK if reports else BAD}{len(reports)} lost reports on sam@campus.edu")
    failures += (not found_n) + (not reports)

    print("\nRetrieval (this is the call that would stall in front of your supervisor)")
    if reports:
        started = time.time()
        matches = get(f"{APP}/matches/{reports[0]['id']}?k=5", token, timeout=300)
        elapsed = time.time() - started
        if matches:
            top = matches[0]
            print(f"{OK}top match F-{top['item']['id']:03d} "
                  f"cos {top['score']:.3f} in {elapsed:.2f}s")
            print(f"       \"{reports[0]['description']}\"")
            print(f"       -> {top['item']['description']}")
            if elapsed > 3:
                print(f"{WARN}that was slow; run check once more so the caches are warm")
        else:
            print(f"{BAD}no matches returned")
            failures += 1

    photos = [p for p in (ROOT / "uploads").glob("*") if p.name != ".gitkeep"]
    print(f"\n{OK if photos else WARN}{len(photos)} photos on disk")
    if not photos:
        print("       cards will show 'no file' placeholders instead of images")

    print()
    if failures:
        print(f"{failures} problem(s) above. Fix before demoing.")
        return 1
    print("Ready. Open http://localhost:5173 and sign in as sam@campus.edu / passw0rd123")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["reset", "check"])
    sys.exit(reset() if parser.parse_args().command == "reset" else check())
