"""Phase 2 checkpoint: CLIP encoding + FAISS retrieval.

Confirms that a text description of a lost item retrieves the photograph of the
matching found item — zero-shot, with no training on campus data.

    uv run python tests/fixtures/download_fixtures.py   # once
    uv run pytest tests/test_phase2_retrieval.py -v -s

Slow: the first run loads a ~600 MB checkpoint. Deselect with `-m "not slow"`.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from backend import clip_encoder, faiss_store  # noqa: E402

pytestmark = pytest.mark.slow

FIXTURES = Path(__file__).parent / "fixtures" / "images"

# Each photograph paired with the kind of description a student would actually
# type into the "I lost..." box.
PAIRS = {
    "backpack": "a photo of a backpack",
    "bicycle": "a photo of a bicycle",
    "eyeglasses": "a photo of a pair of eyeglasses",
    "headphones": "a photo of a pair of headphones",
    "keys": "a photo of a set of keys on a keyring",
    "laptop": "a photo of a laptop computer",
    "umbrella": "a photo of an open umbrella",
    "wallet": "a photo of a leather wallet",
    "water_bottle": "a photo of a reusable water bottle",
    "wristwatch": "a photo of a wristwatch",
}


@pytest.fixture(scope="module")
def dataset():
    slugs = sorted(s for s in PAIRS if (FIXTURES / f"{s}.jpg").exists())
    if len(slugs) < 5:
        pytest.skip(
            f"Only {len(slugs)} image fixtures present. "
            "Run: uv run python tests/fixtures/download_fixtures.py"
        )
    clip_encoder.load_model()
    return {
        "slugs": slugs,
        "paths": [str(FIXTURES / f"{s}.jpg") for s in slugs],
        "texts": [PAIRS[s] for s in slugs],
        "images": clip_encoder.encode_images([str(FIXTURES / f"{s}.jpg") for s in slugs]),
        "text_vecs": clip_encoder.encode_texts([PAIRS[s] for s in slugs]),
    }


@pytest.fixture(autouse=True)
def clean_index():
    faiss_store.reset_index()
    yield
    faiss_store.reset_index()


# --------------------------------------------------------------------------- #
# Encoder contract
# --------------------------------------------------------------------------- #
def test_embeddings_are_512d_unit_norm_float32(dataset):
    for name in ("images", "text_vecs"):
        matrix = dataset[name]
        assert matrix.shape == (len(dataset["slugs"]), 512), name
        assert matrix.dtype == np.float32, name
        np.testing.assert_allclose(np.linalg.norm(matrix, axis=1), 1.0, atol=1e-5)


def test_single_and_batch_encoders_agree(dataset):
    single = clip_encoder.encode_image(dataset["paths"][0])
    assert single.shape == (512,)
    np.testing.assert_allclose(single, dataset["images"][0], atol=1e-5)

    np.testing.assert_allclose(
        clip_encoder.encode_text(dataset["texts"][0]), dataset["text_vecs"][0], atol=1e-5
    )


def test_encode_combined_is_unit_norm_and_between_its_parts(dataset):
    path, text = dataset["paths"][0], dataset["texts"][0]
    combined = clip_encoder.encode_combined(text, path)

    assert combined.shape == (512,)
    assert combined.dtype == np.float32
    assert float(np.linalg.norm(combined)) == pytest.approx(1.0, abs=1e-5)

    # An average of two unit vectors is closer to each of them than they are to
    # each other — this is what lets one index serve text-only, image-only and
    # text+image lost reports.
    to_image = clip_encoder.cosine_similarity(combined, dataset["images"][0])
    to_text = clip_encoder.cosine_similarity(combined, dataset["text_vecs"][0])
    cross = clip_encoder.cosine_similarity(dataset["images"][0], dataset["text_vecs"][0])
    assert to_image > cross and to_text > cross

    # Degenerate inputs fall back to the single available modality.
    np.testing.assert_allclose(
        clip_encoder.encode_combined(text, None), dataset["text_vecs"][0], atol=1e-5
    )
    with pytest.raises(ValueError):
        clip_encoder.encode_combined(None, None)


# --------------------------------------------------------------------------- #
# The actual retrieval claim
# --------------------------------------------------------------------------- #
def test_text_description_retrieves_matching_photo(dataset, capsys):
    """The Phase 2 checkpoint: cross-modal top-1 retrieval on real photos."""
    slugs, images, texts = dataset["slugs"], dataset["images"], dataset["text_vecs"]

    for position, slug in enumerate(slugs):
        assert faiss_store.add_embedding(faiss_store.FOUND, images[position], item_id=position) == position
    assert faiss_store.size(faiss_store.FOUND) == len(slugs)

    hits_at_1 = hits_at_3 = 0
    reciprocal_ranks = []
    with capsys.disabled():
        print(f"\n  {'query':<14} {'score':>7}  rank  top-1 result")
        for position, slug in enumerate(slugs):
            results = faiss_store.search(faiss_store.FOUND, texts[position], k=len(slugs))
            ranked = [r["item_id"] for r in results]
            rank = ranked.index(position) + 1

            hits_at_1 += rank == 1
            hits_at_3 += rank <= 3
            reciprocal_ranks.append(1.0 / rank)
            print(
                f"  {slug:<14} {results[0]['score']:>7.4f}  {rank:>4}  "
                f"{slugs[ranked[0]]}{'' if rank == 1 else '   <-- MISS'}"
            )

        n = len(slugs)
        print(
            f"\n  P@1 {hits_at_1}/{n}   P@3 {hits_at_3}/{n}   "
            f"MRR {np.mean(reciprocal_ranks):.3f}"
        )

    assert hits_at_1 >= 0.8 * len(slugs), "cross-modal top-1 retrieval below 80%"
    assert hits_at_3 == len(slugs), "a correct photo fell outside the top 3"


def test_matching_pairs_score_far_above_mismatched_pairs(dataset):
    """Correct pairings must be separable from wrong ones, not merely ranked."""
    similarity = dataset["text_vecs"] @ dataset["images"].T
    diagonal = np.diag(similarity)
    off_diagonal = similarity[~np.eye(len(dataset["slugs"]), dtype=bool)]

    assert diagonal.mean() > off_diagonal.mean() + 0.10
    assert diagonal.min() > off_diagonal.mean()
    # Raw CLIP cosine lands around 0.2-0.35 for a true match, not near 1.0.
    assert 0.15 < diagonal.mean() < 0.60


def test_scores_are_cosine_similarity(dataset):
    """IndexFlatIP over unit vectors must reproduce the brute-force dot product."""
    images, texts = dataset["images"], dataset["text_vecs"]
    for position in range(len(dataset["slugs"])):
        faiss_store.add_embedding(faiss_store.FOUND, images[position], item_id=position)

    results = faiss_store.search(faiss_store.FOUND, texts[0], k=3)
    for result in results:
        expected = float(np.dot(texts[0], images[result["item_id"]]))
        assert result["score"] == pytest.approx(expected, abs=1e-5)


# --------------------------------------------------------------------------- #
# Store mechanics — exercised with cheap synthetic vectors
# --------------------------------------------------------------------------- #
def _unit(seed: int) -> np.ndarray:
    vector = np.random.default_rng(seed).normal(size=512).astype(np.float32)
    return vector / np.linalg.norm(vector)


def test_found_and_lost_indexes_are_independent():
    faiss_store.add_embedding(faiss_store.FOUND, _unit(1), item_id=11)
    faiss_store.add_embedding(faiss_store.LOST, _unit(2), item_id=22)

    assert faiss_store.size(faiss_store.FOUND) == 1
    assert faiss_store.size(faiss_store.LOST) == 1
    assert faiss_store.search(faiss_store.FOUND, _unit(1), k=5)[0]["item_id"] == 11
    assert faiss_store.search(faiss_store.LOST, _unit(1), k=5)[0]["item_id"] == 22


def test_empty_index_and_k_bounds():
    assert faiss_store.search(faiss_store.FOUND, _unit(0), k=5) == []
    faiss_store.add_embedding(faiss_store.FOUND, _unit(1), item_id=1)
    faiss_store.add_embedding(faiss_store.FOUND, _unit(2), item_id=2)
    # k larger than the index returns everything, not an error.
    assert len(faiss_store.search(faiss_store.FOUND, _unit(1), k=50)) == 2
    assert len(faiss_store.search(faiss_store.FOUND, _unit(1), k=1)) == 1
    assert faiss_store.search(faiss_store.FOUND, _unit(1), k=0) == []


def test_soft_delete_hides_item_without_renumbering_others():
    positions = [faiss_store.add_embedding(faiss_store.FOUND, _unit(i), item_id=i) for i in range(5)]
    assert positions == [0, 1, 2, 3, 4]

    faiss_store.remove_embedding(faiss_store.FOUND, 2)

    results = faiss_store.search(faiss_store.FOUND, _unit(2), k=5)
    assert 2 not in [r["item_id"] for r in results]
    assert faiss_store.size(faiss_store.FOUND) == 4
    # Crucially, item 4 is still at position 4 — every embedding_id in SQLite
    # remains valid after a delete.
    assert [r for r in faiss_store.search(faiss_store.FOUND, _unit(4), k=5) if r["item_id"] == 4][
        0
    ]["embedding_id"] == 4


def test_over_fetch_still_returns_k_live_results():
    for i in range(10):
        faiss_store.add_embedding(faiss_store.FOUND, _unit(i), item_id=i)
    for position in range(5):
        faiss_store.remove_embedding(faiss_store.FOUND, position)

    # 5 live vectors remain; asking for 5 must yield 5 despite the tombstones
    # sitting near the top of the raw neighbour list.
    assert len(faiss_store.search(faiss_store.FOUND, _unit(0), k=5)) == 5


def test_exclude_item_ids():
    for i in range(4):
        faiss_store.add_embedding(faiss_store.FOUND, _unit(i), item_id=i)
    results = faiss_store.search(faiss_store.FOUND, _unit(1), k=4, exclude_item_ids={1})
    assert 1 not in [r["item_id"] for r in results]
    assert len(results) == 3


def test_min_score_filter():
    faiss_store.add_embedding(faiss_store.FOUND, _unit(1), item_id=1)
    faiss_store.add_embedding(faiss_store.FOUND, _unit(2), item_id=2)
    # A vector is at cosine 1.0 with itself; two random 512-d vectors are ~0.
    results = faiss_store.search(faiss_store.FOUND, _unit(1), k=5, min_score=0.9)
    assert [r["item_id"] for r in results] == [1]


def test_rebuild_compacts_and_returns_position_remap():
    for i in range(5):
        faiss_store.add_embedding(faiss_store.FOUND, _unit(i), item_id=i)
    faiss_store.remove_embedding(faiss_store.FOUND, 1)
    faiss_store.remove_embedding(faiss_store.FOUND, 3)

    remap = faiss_store.rebuild(faiss_store.FOUND)

    assert remap == {0: 0, 2: 1, 4: 2}
    assert faiss_store.size(faiss_store.FOUND) == 3
    # Vectors survive the compaction intact and answer at their new positions.
    hit = faiss_store.search(faiss_store.FOUND, _unit(4), k=1)[0]
    assert hit["item_id"] == 4
    assert hit["embedding_id"] == remap[4]
    assert hit["score"] == pytest.approx(1.0, abs=1e-4)

    assert faiss_store.rebuild(faiss_store.FOUND) == {}  # nothing left to compact


def test_save_and_load_round_trip():
    for i in range(3):
        faiss_store.add_embedding(faiss_store.FOUND, _unit(i), item_id=100 + i)
    faiss_store.remove_embedding(faiss_store.FOUND, 1)
    faiss_store.add_embedding(faiss_store.LOST, _unit(9), item_id=999)
    faiss_store.save_index()

    faiss_store.load_index()  # drops in-memory state, re-reads from disk

    assert faiss_store.size(faiss_store.FOUND) == 2
    assert faiss_store.size(faiss_store.LOST) == 1
    assert faiss_store.search(faiss_store.FOUND, _unit(2), k=1)[0]["item_id"] == 102
    assert 101 not in [r["item_id"] for r in faiss_store.search(faiss_store.FOUND, _unit(1), k=3)]
    assert faiss_store.search(faiss_store.LOST, _unit(9), k=1)[0]["item_id"] == 999


def test_wrong_dimension_is_rejected():
    with pytest.raises(ValueError):
        faiss_store.add_embedding(faiss_store.FOUND, np.zeros(256, dtype=np.float32), item_id=1)
    with pytest.raises(ValueError):
        faiss_store.add_embedding("nonsense", _unit(1), item_id=1)
