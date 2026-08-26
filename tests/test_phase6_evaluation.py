"""Phase 6 checkpoint: CLIP retrieval must outperform the TF-IDF baseline.

The metric code is tested on synthetic data (always), and the real comparison
runs against the COCO test set when it has been built:

    uv run python eval/build_dataset.py --n 200
    uv run pytest tests/test_phase6_evaluation.py -v -s
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("CLIP_DEVICE", "cpu")

from eval.baseline import score_matrix  # noqa: E402
from eval.metrics import ranks_from_scores, summarise  # noqa: E402

MANIFEST = Path(__file__).parent.parent / "eval" / "data" / "testset.json"


# --------------------------------------------------------------------------- #
# Metric correctness — no models, always runs
# --------------------------------------------------------------------------- #
def test_perfect_ranking_scores_one():
    scores = np.eye(10)
    metrics = summarise(ranks_from_scores(scores))
    assert metrics["recall@1"] == 1.0
    assert metrics["mrr"] == 1.0
    assert metrics["precision@5"] == pytest.approx(0.2)


def test_correct_item_second_gives_half_mrr():
    scores = np.zeros((4, 4))
    for i in range(4):
        scores[i, i] = 0.5           # correct
        scores[i, (i + 1) % 4] = 0.9  # a decoy ranked above it
    metrics = summarise(ranks_from_scores(scores))
    assert metrics["recall@1"] == 0.0
    assert metrics["recall@3"] == 1.0
    assert metrics["mrr"] == pytest.approx(0.5)


def test_ties_are_broken_pessimistically():
    """All-equal scores must not look like a perfect result."""
    metrics = summarise(ranks_from_scores(np.ones((8, 8))))
    assert metrics["recall@1"] == 0.0
    assert metrics["median_rank"] == 8


def test_tfidf_baseline_ranks_matching_text_first():
    queries = ["a black umbrella with a wooden handle", "a silver laptop computer"]
    listings = ["silver laptop on a desk", "black umbrella, wooden handle, open"]
    # Item i is correct for query i, so the listings are ordered to match.
    scores = score_matrix(queries, [listings[1], listings[0]])
    assert summarise(ranks_from_scores(scores))["recall@1"] == 1.0


# --------------------------------------------------------------------------- #
# The real comparison
# --------------------------------------------------------------------------- #
@pytest.mark.slow
def test_clip_outperforms_tfidf_on_the_test_set(capsys):
    if not MANIFEST.exists():
        pytest.skip("No test set. Run: uv run python eval/build_dataset.py --n 200")

    records = json.loads(MANIFEST.read_text())
    if len(records) < 50:
        pytest.skip(f"Test set has only {len(records)} pairs; need at least 50")

    from backend import clip_encoder

    clip_encoder.load_model()
    images = clip_encoder.encode_images([r["image_path"] for r in records])
    queries = clip_encoder.encode_texts([r["query"] for r in records])

    clip_ranks = ranks_from_scores(queries @ images.T)
    tfidf_ranks = ranks_from_scores(
        score_matrix([r["query"] for r in records], [r["listing"] for r in records])
    )

    clip_metrics = summarise(clip_ranks)
    tfidf_metrics = summarise(tfidf_ranks)

    with capsys.disabled():
        print(f"\n  {'':<8} {'R@1':>7} {'R@3':>7} {'R@5':>7} {'MRR':>7}")
        for name, m in (("clip", clip_metrics), ("tfidf", tfidf_metrics)):
            print(f"  {name:<8} {m['recall@1']:>7.3f} {m['recall@3']:>7.3f} "
                  f"{m['recall@5']:>7.3f} {m['mrr']:>7.3f}")

    # The project's central claim: zero-shot vision-language retrieval beats
    # keyword matching, without a single item of campus training data.
    assert clip_metrics["recall@1"] > tfidf_metrics["recall@1"]
    assert clip_metrics["recall@5"] > tfidf_metrics["recall@5"]
    assert clip_metrics["mrr"] > tfidf_metrics["mrr"]

    # Guard against a silent regression in the encoder or the index.
    assert clip_metrics["recall@1"] > 0.45, "CLIP R@1 far below the measured 0.625"
    assert clip_metrics["recall@5"] > 0.80, "CLIP R@5 far below the measured 0.950"
