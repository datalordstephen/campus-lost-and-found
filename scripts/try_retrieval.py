"""Manual retrieval playground — try CLIP matching on your own photos.

Phase 3 puts this behind HTTP endpoints; until then this is the way to poke at it.

    # Score every fixture photo against a description you type
    uv run python scripts/try_retrieval.py "a black umbrella"

    # Use your own photos as the "found item" pool
    uv run python scripts/try_retrieval.py "my blue water bottle" --images ~/Desktop/photos

    # Compare one description against one photo
    uv run python scripts/try_retrieval.py "a laptop" --image tests/fixtures/images/laptop.jpg
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import clip_encoder, faiss_store  # noqa: E402

SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic"}
DEFAULT_IMAGES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "images"


def collect(directory: Path) -> list[Path]:
    return sorted(p for p in directory.iterdir() if p.suffix.lower() in SUFFIXES)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("description", help='what was lost, e.g. "a red backpack"')
    parser.add_argument("--images", type=Path, default=DEFAULT_IMAGES, help="folder of photos")
    parser.add_argument("--image", type=Path, help="score against this single photo instead")
    parser.add_argument("-k", type=int, default=5, help="how many matches to show")
    args = parser.parse_args()

    print("Loading OpenCLIP (first run downloads ~600 MB)...", flush=True)
    clip_encoder.load_model()
    query = clip_encoder.encode_text(args.description)

    if args.image:
        score = clip_encoder.cosine_similarity(query, clip_encoder.encode_image(str(args.image)))
        print(f"\n  {args.description!r}  vs  {args.image.name}")
        print(f"  cosine similarity: {score:.4f}")
        print("\n  Reference: a correct pair scores ~0.22-0.33, an unrelated pair ~0.13.")
        return 0

    if not args.images.is_dir():
        print(f"No such folder: {args.images}", file=sys.stderr)
        return 1
    paths = collect(args.images)
    if not paths:
        print(f"No images in {args.images}", file=sys.stderr)
        return 1

    print(f"Encoding {len(paths)} photos from {args.images}...", flush=True)
    embeddings = clip_encoder.encode_images([str(p) for p in paths])

    # Same code path the API will use in Phase 3.
    faiss_store.reset_index()
    for position, embedding in enumerate(embeddings):
        faiss_store.add_embedding(faiss_store.FOUND, embedding, item_id=position)

    results = faiss_store.search(faiss_store.FOUND, query, k=min(args.k, len(paths)))

    print(f"\n  Query: {args.description!r}\n")
    print(f"  {'#':<3} {'score':>7}  photo")
    print(f"  {'-' * 3} {'-' * 7}  {'-' * 30}")
    for rank, result in enumerate(results, start=1):
        print(f"  {rank:<3} {result['score']:>7.4f}  {paths[result['item_id']].name}")

    spread = results[0]["score"] - float(np.mean([r["score"] for r in results[1:]] or [0]))
    print(f"\n  Top-1 leads the rest by {spread:+.4f}.")
    print("  Reference: a correct pair scores ~0.22-0.33, an unrelated pair ~0.13.")
    faiss_store.reset_index()
    return 0


if __name__ == "__main__":
    sys.exit(main())
