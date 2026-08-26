"""Administrative endpoints — user management, stale listing removal, statistics."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend import faiss_store
from backend.auth import role_required
from backend.database import get_db
from backend.models import (
    Claim,
    ClaimStatus,
    FoundItem,
    LostItem,
    User,
    UserRole,
)
from backend.schemas import Message, SystemStats, UserOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))


@router.get("/users", response_model=list[UserOut])
def list_users(
    role: UserRole | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(role_required(UserRole.admin)),
) -> list[User]:
    query = select(User).order_by(User.created_at.desc())
    if role is not None:
        query = query.where(User.role == role)
    return list(db.scalars(query.limit(limit).offset(offset)).all())


@router.patch("/users/{user_id}/role", response_model=UserOut)
def change_user_role(
    user_id: int,
    role: UserRole,
    db: Session = Depends(get_db),
    current_user: User = Depends(role_required(UserRole.admin)),
) -> User:
    """Promote or demote an account — the intended way to create staff."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_user.id and role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove your own admin role",
        )
    user.role = role
    db.commit()
    db.refresh(user)
    return user


def _delete_item(db: Session, item, kind: str) -> None:
    """Drop a listing, its vector, and its orphaned photo."""
    if item.embedding_id is not None:
        faiss_store.remove_embedding(kind, item.embedding_id)

    image_path = item.image_path
    db.delete(item)
    db.commit()
    faiss_store.save_index()

    # Uploads are content-hashed, so the same file may back several rows.
    if image_path:
        still_referenced = db.scalar(
            select(func.count(FoundItem.id)).where(FoundItem.image_path == image_path)
        ) or 0
        still_referenced += db.scalar(
            select(func.count(LostItem.id)).where(LostItem.image_path == image_path)
        ) or 0
        if still_referenced == 0:
            Path(image_path).unlink(missing_ok=True)


@router.delete("/items/found/{item_id}", response_model=Message)
def delete_found_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(role_required(UserRole.admin)),
) -> Message:
    item = db.get(FoundItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Found item not found")
    if item.claims:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete an item that has claims against it",
        )
    _delete_item(db, item, faiss_store.FOUND)
    logger.info("Admin %s deleted found item %s", current_user.id, item_id)
    return Message(detail=f"Found item {item_id} removed")


@router.delete("/items/lost/{item_id}", response_model=Message)
def delete_lost_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(role_required(UserRole.admin)),
) -> Message:
    item = db.get(LostItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lost item not found")
    if item.claims:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a report that has claims against it",
        )
    _delete_item(db, item, faiss_store.LOST)
    logger.info("Admin %s deleted lost item %s", current_user.id, item_id)
    return Message(detail=f"Lost item {item_id} removed")


@router.get("/stats", response_model=SystemStats)
def system_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(role_required(UserRole.admin)),
) -> SystemStats:
    by_role = dict(
        db.execute(select(User.role, func.count(User.id)).group_by(User.role)).all()
    )
    index_stats = faiss_store.stats()
    return SystemStats(
        total_users=db.scalar(select(func.count(User.id))) or 0,
        users_by_role={
            role.value if hasattr(role, "value") else str(role): count
            for role, count in by_role.items()
        },
        total_found_items=db.scalar(select(func.count(FoundItem.id))) or 0,
        total_lost_items=db.scalar(select(func.count(LostItem.id))) or 0,
        total_claims=db.scalar(select(func.count(Claim.id))) or 0,
        claims_released=db.scalar(
            select(func.count(Claim.id)).where(Claim.status == ClaimStatus.released)
        ) or 0,
        faiss_vectors=sum(s["live"] for s in index_stats.values()),
    )


@router.post("/index/rebuild", response_model=Message)
def rebuild_index(
    db: Session = Depends(get_db),
    current_user: User = Depends(role_required(UserRole.admin)),
) -> Message:
    """Compact tombstoned vectors out of both indexes.

    The remap must be applied to SQLite in the same breath — a stale
    ``embedding_id`` would point at another item's vector.
    """
    moved = 0
    for kind, model in ((faiss_store.FOUND, FoundItem), (faiss_store.LOST, LostItem)):
        remap = faiss_store.rebuild(kind)
        if not remap:
            continue
        for row in db.scalars(select(model).where(model.embedding_id.isnot(None))).all():
            row.embedding_id = remap.get(row.embedding_id)  # None if it was deleted
        moved += len(remap)
    db.commit()
    faiss_store.save_index()
    return Message(detail=f"Index rebuilt; {moved} vectors repositioned")
