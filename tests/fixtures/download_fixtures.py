"""Fetch a small set of real photographs of common campus lost-item categories.

Images come from Wikimedia Commons (freely licensed) and land in
``tests/fixtures/images/``. They are gitignored — run this once per checkout:

    uv run python tests/fixtures/download_fixtures.py

The Phase 2 retrieval test uses them when present and falls back to synthetic
shapes when the machine is offline.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

IMAGES_DIR = Path(__file__).parent / "images"
API = "https://commons.wikimedia.org/w/api.php"
UA = "campus-lost-found-dev/0.1 (research project; contact via repository)"

# slug -> Commons search term. One clean photo per everyday lost-item category.
QUERIES = {
    "backpack": "backpack bag",
    "umbrella": "umbrella open",
    "water_bottle": "reusable water bottle",
    "laptop": "laptop computer",
    "bicycle": "bicycle",
    "eyeglasses": "eyeglasses spectacles",
    "wristwatch": "wristwatch",
    "headphones": "headphones",
    "keys": "keys keyring",
    "wallet": "leather wallet",
}


def _get(url: str, attempts: int = 4) -> bytes:
    """Fetch with exponential backoff — Commons rate-limits bursts with HTTP 429."""
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 503) or attempt == attempts - 1:
                raise
            time.sleep(3 * 2**attempt)
    raise RuntimeError("unreachable")


def _first_thumb_url(term: str) -> str | None:
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"filetype:bitmap {term}",
            "gsrlimit": "1",
            "gsrnamespace": "6",
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": "512",
            "format": "json",
        }
    )
    pages = json.loads(_get(f"{API}?{params}")).get("query", {}).get("pages", {})
    for page in pages.values():
        info = page.get("imageinfo", [{}])[0]
        if url := info.get("thumburl"):
            return url
    return None


def main() -> int:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    failures = []

    for slug, term in QUERIES.items():
        destination = IMAGES_DIR / f"{slug}.jpg"
        if destination.exists():
            print(f"  cached  {slug}")
            manifest[slug] = destination.name
            continue
        try:
            url = _first_thumb_url(term)
            if not url:
                raise RuntimeError("no search result")
            destination.write_bytes(_get(url))
            manifest[slug] = destination.name
            print(f"  fetched {slug:14s} {destination.stat().st_size // 1024:>4d} KB")
            time.sleep(1.5)  # be a good Commons citizen
        except Exception as exc:  # noqa: BLE001 — best-effort fixture fetch
            failures.append(slug)
            print(f"  FAILED  {slug:14s} {exc}")

    (IMAGES_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"\n{len(manifest)}/{len(QUERIES)} fixtures in {IMAGES_DIR}")
    return 1 if failures and not manifest else 0


if __name__ == "__main__":
    sys.exit(main())
