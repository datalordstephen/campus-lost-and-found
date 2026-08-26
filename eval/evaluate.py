"""Phase 6: does zero-shot CLIP retrieval beat a keyword baseline?

Runs every query against the whole gallery and reports P@k, R@k and MRR at
k = 1, 3, 5, for:

  clip                  lost report -> photograph (the system as built)
  clip + "a photo of"   the same, with the standard zero-shot prompt template
  clip (combined)       photograph averaged with the finder's own description,
                        which is what backend/items.py actually indexes when a
                        found item is submitted with text
  tfidf                 lost report -> finder's description (the baseline)

    uv run python eval/evaluate.py
    uv run python eval/evaluate.py --json eval/results.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.baseline import score_matrix  # noqa: E402
from eval.metrics import ranks_from_scores, summarise, table  # noqa: E402

MANIFEST = Path(__file__).parent / "data" / "testset.json"


def bootstrap_ci(ranks: np.ndarray, k: int, rounds: int = 2000, seed: int = 0) -> tuple[float, float]:
    """95% CI on R@k by resampling queries — the set is only ~200 items, so a
    bare point estimate would overstate how precisely we know the difference."""
    rng = np.random.default_rng(seed)
    n = len(ranks)
    draws = [np.mean(ranks[rng.integers(0, n, n)] <= k) for _ in range(rounds)]
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def paired_bootstrap(a: np.ndarray, b: np.ndarray, k: int, rounds: int = 2000, seed: int = 0) -> float:
    """One-sided p-value that method A beats method B at R@k, resampling the
    same queries for both so the pairing is preserved."""
    rng = np.random.default_rng(seed)
    n = len(a)
    observed = np.mean(a <= k) - np.mean(b <= k)
    if observed <= 0:
        return 1.0
    wins = 0
    for _ in range(rounds):
        idx = rng.integers(0, n, n)
        if (np.mean(a[idx] <= k) - np.mean(b[idx] <= k)) <= 0:
            wins += 1
    return wins / rounds


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="also write the results here")
    parser.add_argument("--limit", type=int, help="use only the first N pairs (smoke test)")
    args = parser.parse_args()

    if not MANIFEST.exists():
        sys.exit(f"No test set at {MANIFEST}. Run: uv run python eval/build_dataset.py")

    records = json.loads(MANIFEST.read_text())
    if args.limit:
        records = records[: args.limit]

    queries = [r["query"] for r in records]
    listings = [r["listing"] for r in records]
    paths = [r["image_path"] for r in records]
    n = len(records)
    print(f"{n} query/item pairs, {len({r['category'] for r in records})} categories\n")

    from backend import clip_encoder

    started = time.time()
    clip_encoder.load_model()
    print(f"model loaded in {time.time() - started:.1f}s; encoding...")

    started = time.time()
    image_vecs = clip_encoder.encode_images(paths)
    query_vecs = clip_encoder.encode_texts(queries)
    templated = clip_encoder.encode_texts([f"a photo of {q}" for q in queries])
    listing_vecs = clip_encoder.encode_texts(listings)
    print(f"encoded {n} images + {3 * n} texts in {time.time() - started:.1f}s\n")

    # What items.py stores for a found item that arrived with a description.
    combined = image_vecs + listing_vecs
    combined /= np.linalg.norm(combined, axis=1, keepdims=True)

    runs = {
        "clip (text -> image)": query_vecs @ image_vecs.T,
        'clip + "a photo of"': templated @ image_vecs.T,
        "clip (text -> image+desc)": query_vecs @ combined.T,
        "tfidf (text -> text)": score_matrix(queries, listings),
    }

    ranks = {name: ranks_from_scores(scores) for name, scores in runs.items()}
    results = {name: summarise(r) for name, r in ranks.items()}

    print(table(results))

    print("\n95% CI on R@1 (bootstrap over queries)")
    for name, r in ranks.items():
        low, high = bootstrap_ci(r, 1)
        print(f"  {name:<28} {np.mean(r <= 1):.3f}  [{low:.3f}, {high:.3f}]")

    baseline = ranks["tfidf (text -> text)"]
    print("\nvs. the TF-IDF baseline (paired bootstrap, one-sided)")
    for name, r in ranks.items():
        if name == "tfidf (text -> text)":
            continue
        for k in (1, 5):
            delta = np.mean(r <= k) - np.mean(baseline <= k)
            p = paired_bootstrap(r, baseline, k)
            verdict = "significant" if p < 0.05 else "not significant"
            print(f"  {name:<28} R@{k}  {delta:+.3f}  p={p:.4f}  {verdict}")

    # Where does it fail? Useful for the write-up.
    worst = sorted(zip(ranks["clip (text -> image)"], records), key=lambda t: -t[0])[:5]
    print("\nworst CLIP retrievals")
    for rank, record in worst:
        print(f"  rank {int(rank):>3}  [{record['category']}]  {record['query'][:70]}")

    if args.json:
        args.json.write_text(json.dumps({
            "n": n,
            "results": results,
            "ranks": {k: v.tolist() for k, v in ranks.items()},
        }, indent=2))
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
