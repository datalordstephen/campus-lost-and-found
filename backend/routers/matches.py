"""Retrieval endpoints — the top-k cross-modal matches for an existing item.

Both routes reuse the vector already sitting in FAISS rather than re-encoding the
item, so a dashboard refresh costs a dot product instead of a CLIP forward pass.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend import clip_encoder, faiss_store
from backend.auth import role_required
from backend.database import get_db
from backend.models import FoundItem, LostItem, User, UserRole
from backend.routers.items import match_found_for, match_lost_for
from backend.schemas import FoundItemMatch, LostItemMatch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/matches", tags=["matches"])


def _query_vector_for(item, kind: str):
    """The item's stored embedding, re-encoding only if the index lost it."""
    if item.embedding_id is not None:
        vector = faiss_store.get_embedding(kind, item.embedding_id)
        if vector is not None:
            return vector

    # Index was rebuilt from scratch or the snapshot was lost — fall back to CLIP.
    logger.warning(
        "No stored vector for %s id=%s (embedding_id=%s); re-encoding",
        kind,
        item.id,
        item.embedding_id,
    )
    # Both models expose .description; only LostItem may lack an image.
    return clip_encoder.encode_combined(item.description, item.image_path)


# Declared before the single-segment route so "/matches/found/3" is never read
# as a lost-item id.
@router.get("/found/{found_item_id}", response_model=list[LostItemMatch])
def matches_for_found_item(
    found_item_id: int,
    k: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(role_required(UserRole.security, UserRole.admin)),
) -> list[LostItemMatch]:
    """Which open lost reports could this handed-in item belong to?"""
    item = db.get(FoundItem, found_item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Found item not found")

    return match_lost_for(db, _query_vector_for(item, faiss_store.FOUND), k)


@router.get("/{lost_item_id}", response_model=list[FoundItemMatch])
def matches_for_lost_item(
    lost_item_id: int,
    k: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        role_required(UserRole.student, UserRole.security, UserRole.admin)
    ),
) -> list[FoundItemMatch]:
    """Which found items look like the thing this student lost?"""
    item = db.get(LostItem, lost_item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lost item not found")

    # A student sees only their own report's matches; staff can review any.
    if current_user.role == UserRole.student and item.reported_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view matches for your own lost item reports",
        )

    return match_found_for(db, _query_vector_for(item, faiss_store.LOST), k)
