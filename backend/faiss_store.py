"""FAISS vector store — cosine-similarity retrieval over CLIP embeddings.

`IndexFlatIP` computes inner products; because every vector `clip_encoder` emits is
L2-normalised, that inner product *is* the cosine similarity, in [-1, 1].

Two separate indexes
--------------------
The spec sketches a single `index.bin`, but the two retrieval directions never
mix: a lost report is only ever scored against found-item photos, and a found
photo only against open lost reports. Sharing one index would mean over-fetching
and then discarding half the neighbours — with no k that guarantees enough
survivors. So the store keeps a **"found"** index and a **"lost"** index side by
side, in the directory `FAISS_INDEX_PATH` points at.

Deletion
--------
`IndexFlatIP.remove_ids` compacts the array and *renumbers* every vector after the
removed one, which would silently invalidate every `embedding_id` already stored
in SQLite. Instead a removal is a soft delete: the position is recorded in a
tombstone set and filtered out at search time. `rebuild()` does the real compaction
and hands back an old→new position map so the DB can be migrated in the same
transaction.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

import faiss
import numpy as np
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

EMBED_DIM = 512
FOUND = "found"
LOST = "lost"
KINDS = (FOUND, LOST)

INDEX_DIR = Path(os.getenv("FAISS_INDEX_PATH", "./faiss_index/index.bin")).parent

_lock = threading.RLock()


@dataclass
class _Store:
    kind: str
    index: faiss.Index
    item_ids: list[int] = field(default_factory=list)  # FAISS position -> DB row id
    deleted: set[int] = field(default_factory=set)  # tombstoned positions

    @property
    def live_count(self) -> int:
        return self.index.ntotal - len(self.deleted)


_stores: dict[str, _Store] = {}


def _new_index() -> faiss.Index:
    return faiss.IndexFlatIP(EMBED_DIM)


def _paths(kind: str) -> tuple[Path, Path]:
    return INDEX_DIR / f"{kind}.bin", INDEX_DIR / f"{kind}.meta.json"


def _get(kind: str) -> _Store:
    if kind not in KINDS:
        raise ValueError(f"Unknown index kind {kind!r}; expected one of {KINDS}")
    if kind not in _stores:
        init_index()
    return _stores[kind]


def _as_matrix(embedding: np.ndarray) -> np.ndarray:
    """Coerce to a contiguous (1, 512) float32 unit-norm row."""
    vec = np.asarray(embedding, dtype=np.float32).reshape(1, -1)
    if vec.shape[1] != EMBED_DIM:
        raise ValueError(f"Expected a {EMBED_DIM}-dim embedding, got {vec.shape[1]}")
    norm = float(np.linalg.norm(vec))
    if norm > 0 and abs(norm - 1.0) > 1e-3:
        # Should not happen — clip_encoder normalises — but an un-normalised
        # vector would quietly corrupt every score in the index.
        logger.warning("Embedding had norm %.4f; re-normalising before insert", norm)
        vec = vec / norm
    return np.ascontiguousarray(vec)


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
def init_index() -> None:
    """Create both indexes, restoring from disk when a snapshot exists."""
    with _lock:
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        for kind in KINDS:
            if kind not in _stores:
                _stores[kind] = _load_one(kind)


def _load_one(kind: str) -> _Store:
    index_path, meta_path = _paths(kind)
    if not (index_path.exists() and meta_path.exists()):
        return _Store(kind=kind, index=_new_index())

    try:
        index = faiss.read_index(str(index_path))
        meta = json.loads(meta_path.read_text())
        store = _Store(
            kind=kind,
            index=index,
            item_ids=[int(i) for i in meta.get("item_ids", [])],
            deleted={int(i) for i in meta.get("deleted", [])},
        )
        if index.ntotal != len(store.item_ids):
            # Snapshot torn between the .bin and .json writes — safer to start
            # clean than to serve results mapped to the wrong rows.
            raise ValueError(
                f"{kind}: index has {index.ntotal} vectors but metadata lists "
                f"{len(store.item_ids)} ids"
            )
        logger.info("Loaded FAISS '%s' index: %d vectors (%d live)", kind, index.ntotal, store.live_count)
        return store
    except Exception:
        logger.exception("Could not load FAISS '%s' index; starting empty", kind)
        return _Store(kind=kind, index=_new_index())


def load_index() -> None:
    """Force a re-read from disk, discarding in-memory state."""
    with _lock:
        _stores.clear()
        init_index()


def save_index() -> None:
    """Persist both indexes. Written to a temp file then renamed, so a crash
    mid-write leaves the previous good snapshot intact."""
    with _lock:
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        for kind, store in _stores.items():
            index_path, meta_path = _paths(kind)
            tmp_index, tmp_meta = index_path.with_suffix(".tmp"), meta_path.with_suffix(".tmp")

            faiss.write_index(store.index, str(tmp_index))
            tmp_meta.write_text(
                json.dumps({"item_ids": store.item_ids, "deleted": sorted(store.deleted)})
            )
            os.replace(tmp_index, index_path)
            os.replace(tmp_meta, meta_path)
        logger.info("FAISS indexes saved to %s", INDEX_DIR)


def reset_index() -> None:
    """Drop everything, in memory and on disk. Test/eval helper."""
    with _lock:
        _stores.clear()
        for kind in KINDS:
            for path in _paths(kind):
                path.unlink(missing_ok=True)
        init_index()


# --------------------------------------------------------------------------- #
# Write path
# --------------------------------------------------------------------------- #
def add_embedding(kind: str, embedding: np.ndarray, item_id: int) -> int:
    """Append one vector and return its FAISS position (store as ``embedding_id``)."""
    with _lock:
        store = _get(kind)
        store.index.add(_as_matrix(embedding))
        store.item_ids.append(int(item_id))
        return store.index.ntotal - 1


def remove_embedding(kind: str, embedding_id: int) -> None:
    """Soft-delete a position. Positions of other vectors are unaffected."""
    with _lock:
        store = _get(kind)
        if 0 <= embedding_id < store.index.ntotal:
            store.deleted.add(int(embedding_id))
        else:
            logger.warning("remove_embedding: position %s out of range for '%s'", embedding_id, kind)


def rebuild(kind: str) -> dict[int, int]:
    """Compact away tombstones. Returns ``{old_position: new_position}``.

    Callers must apply the map to ``embedding_id`` in SQLite inside the same
    transaction, otherwise stored positions point at the wrong vectors.
    """
    with _lock:
        store = _get(kind)
        if not store.deleted:
            return {}

        live = [p for p in range(store.index.ntotal) if p not in store.deleted]
        vectors = store.index.reconstruct_n(0, store.index.ntotal)

        new_index = _new_index()
        if live:
            new_index.add(np.ascontiguousarray(vectors[live], dtype=np.float32))

        remap = {old: new for new, old in enumerate(live)}
        _stores[kind] = _Store(
            kind=kind,
            index=new_index,
            item_ids=[store.item_ids[p] for p in live],
        )
        logger.info("Rebuilt '%s': %d -> %d vectors", kind, store.index.ntotal, new_index.ntotal)
        return remap


# --------------------------------------------------------------------------- #
# Read path
# --------------------------------------------------------------------------- #
def search(
    kind: str,
    query_embedding: np.ndarray,
    k: int = 5,
    exclude_item_ids: set[int] | None = None,
    min_score: float | None = None,
) -> list[dict]:
    """Top-k nearest neighbours as ``[{item_id, embedding_id, score}]``, best first.

    Fewer than k entries come back when the index holds fewer live vectors.
    """
    with _lock:
        store = _get(kind)
        if store.index.ntotal == 0 or k <= 0:
            return []

        excluded = exclude_item_ids or set()
        # Over-fetch: tombstoned and excluded neighbours are dropped after the
        # search, so asking for exactly k could return short.
        fetch = min(store.index.ntotal, k + len(store.deleted) + len(excluded))
        scores, positions = store.index.search(_as_matrix(query_embedding), fetch)

        results: list[dict] = []
        for score, position in zip(scores[0], positions[0]):
            if position < 0:  # FAISS pads with -1 when it runs out of candidates
                continue
            position = int(position)
            if position in store.deleted:
                continue
            item_id = store.item_ids[position]
            if item_id in excluded:
                continue
            score = float(score)
            if min_score is not None and score < min_score:
                continue
            results.append({"item_id": item_id, "embedding_id": position, "score": score})
            if len(results) == k:
                break
        return results


# --------------------------------------------------------------------------- #
# Introspection
# --------------------------------------------------------------------------- #
def size(kind: str) -> int:
    """Live (non-tombstoned) vector count."""
    return _get(kind).live_count


def stats() -> dict[str, dict[str, int]]:
    init_index()
    return {
        kind: {
            "total": store.index.ntotal,
            "live": store.live_count,
            "deleted": len(store.deleted),
        }
        for kind, store in _stores.items()
    }


def get_embedding(kind: str, embedding_id: int) -> np.ndarray | None:
    """Recover a stored vector by position.

    Lets the match endpoints re-query with an item's existing embedding instead
    of paying for another CLIP forward pass.
    """
    with _lock:
        store = _get(kind)
        if not (0 <= embedding_id < store.index.ntotal):
            return None
        return store.index.reconstruct(int(embedding_id)).astype(np.float32)
