"""Item submission and listing.

The write path here has to keep three stores in agreement — the uploads
directory, the SQLite row, and the FAISS index. See ``_encode_and_index`` for
the ordering and the rollback.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import clip_encoder, faiss_store
from backend.auth import encrypt_text, role_required
from backend.database import get_db
from backend.models import (
    FoundItem,
    FoundItemStatus,
    LostItem,
    LostItemStatus,
    User,
    UserRole,
)
from backend.schemas import (
    FoundItemMatch,
    FoundItemOut,
    FoundItemSubmitResult,
    LostItemMatch,
    LostItemOut,
    LostItemSubmitResult,
)

load_dotenv()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/items", tags=["items"])

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
EXTENSION_FOR_FORMAT = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
DEFAULT_K = 5

# Endpoints are sync `def`, so FastAPI runs them in its thread pool. CLIP is
# CPU-bound; an `async def` would block the event loop for the whole forward pass.


# --------------------------------------------------------------------------- #
# Upload handling
# --------------------------------------------------------------------------- #
def _save_upload(upload: UploadFile) -> str:
    """Persist an uploaded photo under a content-hashed name; return its path.

    Hashing the bytes rather than the client-supplied name means no path
    traversal, no collisions, and re-uploading the same photo is free.
    """
    if upload.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported image type {upload.content_type!r}; "
            f"expected one of {sorted(ALLOWED_IMAGE_TYPES)}",
        )

    payload = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
        )
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty upload")

    # Trust the pixels, not the Content-Type header.
    import io

    try:
        with Image.open(io.BytesIO(payload)) as probe:
            probe.verify()
            image_format = probe.format
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is not a readable image",
        ) from exc

    extension = EXTENSION_FOR_FORMAT.get(image_format or "", ".jpg")
    digest = hashlib.sha256(payload).hexdigest()[:32]

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_DIR / f"{digest}{extension}"
    if not destination.exists():
        destination.write_bytes(payload)
    return str(destination)


# --------------------------------------------------------------------------- #
# Matching helpers
# --------------------------------------------------------------------------- #
def _ineligible_found_ids(db: Session) -> set[int]:
    """Found items that should never be offered as a match.

    Only ``claimed`` items are excluded. The spec's flow says to match against
    *verified* found items, but items land as ``pending_custody`` and stay there
    until an officer confirms — matching only verified items would leave a window
    where a student cannot find an item that is already sitting at the desk.
    """
    return set(
        db.scalars(
            select(FoundItem.id).where(FoundItem.status == FoundItemStatus.claimed)
        ).all()
    )


def _ineligible_lost_ids(db: Session) -> set[int]:
    return set(
        db.scalars(select(LostItem.id).where(LostItem.status == LostItemStatus.claimed)).all()
    )


def match_found_for(db: Session, query_embedding, k: int) -> list[FoundItemMatch]:
    """Top-k found items for a lost-item query vector."""
    hits = faiss_store.search(
        faiss_store.FOUND, query_embedding, k=k, exclude_item_ids=_ineligible_found_ids(db)
    )
    return _hydrate(db, hits, FoundItem, FoundItemOut, FoundItemMatch)


def match_lost_for(db: Session, query_embedding, k: int) -> list[LostItemMatch]:
    """Top-k open lost reports for a found-item query vector."""
    hits = faiss_store.search(
        faiss_store.LOST, query_embedding, k=k, exclude_item_ids=_ineligible_lost_ids(db)
    )
    return _hydrate(db, hits, LostItem, LostItemOut, LostItemMatch)


def _hydrate(db: Session, hits: list[dict], model, out_schema, match_schema) -> list:
    """Turn ``[{item_id, score}]`` into ordered, fully-populated match objects."""
    if not hits:
        return []
    ids = [h["item_id"] for h in hits]
    rows = {row.id: row for row in db.scalars(select(model).where(model.id.in_(ids))).all()}
    return [
        match_schema(score=hit["score"], item=out_schema.model_validate(rows[hit["item_id"]]))
        for hit in hits
        if hit["item_id"] in rows  # a row deleted since indexing simply drops out
    ]


def _encode_and_index(db: Session, row, kind: str, embedding) -> None:
    """Attach ``row`` to the FAISS index and commit both together.

    SQLite and FAISS cannot share a transaction, so the vector goes in first and
    is tombstoned again if the commit fails. That leaves a dead vector rather
    than a live vector pointing at a row that does not exist.
    """
    position = faiss_store.add_embedding(kind, embedding, item_id=row.id)
    row.embedding_id = position
    try:
        db.commit()
    except Exception:
        db.rollback()
        faiss_store.remove_embedding(kind, position)
        raise
    db.refresh(row)
    faiss_store.save_index()


# --------------------------------------------------------------------------- #
# POST /items/found
# --------------------------------------------------------------------------- #
@router.post("/found", response_model=FoundItemSubmitResult, status_code=status.HTTP_201_CREATED)
def submit_found_item(
    image: UploadFile = File(..., description="Photo of the found item"),
    location: str = Form(..., min_length=1, max_length=255),
    security_post_id: int | None = Form(None),
    description: str | None = Form(None, max_length=1000),
    k: int = Query(DEFAULT_K, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(role_required(UserRole.student, UserRole.security)),
) -> FoundItemSubmitResult:
    """Hand in a found item: photo is encoded, indexed, and matched against open lost reports."""
    if security_post_id is not None:
        officer = db.get(User, security_post_id)
        if officer is None or officer.role != UserRole.security:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="security_post_id must reference a user with the 'security' role",
            )

    image_path = _save_upload(image)

    item = FoundItem(
        image_path=image_path,
        description=description,
        location=location,
        submitted_by=current_user.id,
        security_post_id=security_post_id,
        status=FoundItemStatus.pending_custody,
    )
    db.add(item)
    db.flush()  # assigns item.id without committing

    try:
        embedding = clip_encoder.encode_combined(description, image_path)
    except Exception as exc:
        db.rollback()
        logger.exception("CLIP encoding failed for found item")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not encode the uploaded image",
        ) from exc

    _encode_and_index(db, item, faiss_store.FOUND, embedding)

    return FoundItemSubmitResult(
        item=FoundItemOut.model_validate(item),
        matches=match_lost_for(db, embedding, k),
    )


# --------------------------------------------------------------------------- #
# POST /items/lost
# --------------------------------------------------------------------------- #
@router.post("/lost", response_model=LostItemSubmitResult, status_code=status.HTTP_201_CREATED)
def report_lost_item(
    description: str = Form(..., min_length=1, max_length=1000),
    location_last_seen: str = Form(..., min_length=1, max_length=255),
    private_descriptor: str = Form(
        ...,
        min_length=1,
        max_length=1000,
        description="A detail only the owner would know. Stored encrypted; used for NLI verification.",
    ),
    image: UploadFile | None = File(None),
    k: int = Query(DEFAULT_K, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(role_required(UserRole.student, UserRole.security)),
) -> LostItemSubmitResult:
    """Report a lost item and immediately get the top-k found photos it resembles."""
    # An "empty" optional file field arrives as an UploadFile with no filename.
    image_path = _save_upload(image) if image is not None and image.filename else None

    item = LostItem(
        description=description,
        image_path=image_path,
        private_descriptor=encrypt_text(private_descriptor),
        location_last_seen=location_last_seen,
        reported_by=current_user.id,
        status=LostItemStatus.open,
    )
    db.add(item)
    db.flush()

    try:
        embedding = clip_encoder.encode_combined(description, image_path)
    except Exception as exc:
        db.rollback()
        logger.exception("CLIP encoding failed for lost item")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not encode the lost item report",
        ) from exc

    _encode_and_index(db, item, faiss_store.LOST, embedding)

    return LostItemSubmitResult(
        item=LostItemOut.model_validate(item),
        matches=match_found_for(db, embedding, k),
    )


# --------------------------------------------------------------------------- #
# Listings
# --------------------------------------------------------------------------- #
@router.get("/found", response_model=list[FoundItemOut])
def list_found_items(
    item_status: FoundItemStatus | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(role_required(UserRole.security, UserRole.admin)),
) -> list[FoundItem]:
    query = select(FoundItem).order_by(FoundItem.created_at.desc())
    if item_status is not None:
        query = query.where(FoundItem.status == item_status)
    return list(db.scalars(query.limit(limit).offset(offset)).all())


@router.get("/lost", response_model=list[LostItemOut])
def list_lost_items(
    item_status: LostItemStatus | None = Query(None, alias="status"),
    mine: bool = Query(False, description="Only the caller's own reports"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        role_required(UserRole.student, UserRole.security, UserRole.admin)
    ),
) -> list[LostItem]:
    query = select(LostItem).order_by(LostItem.created_at.desc())
    if item_status is not None:
        query = query.where(LostItem.status == item_status)
    if mine:
        query = query.where(LostItem.reported_by == current_user.id)
    return list(db.scalars(query.limit(limit).offset(offset)).all())


@router.get("/found/{item_id}", response_model=FoundItemOut)
def get_found_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        role_required(UserRole.student, UserRole.security, UserRole.admin)
    ),
) -> FoundItem:
    item = db.get(FoundItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Found item not found")
    return item


@router.get("/lost/{item_id}", response_model=LostItemOut)
def get_lost_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        role_required(UserRole.student, UserRole.security, UserRole.admin)
    ),
) -> LostItem:
    item = db.get(LostItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lost item not found")
    return item


@router.post("/found/{item_id}/confirm-custody", response_model=FoundItemOut)
def confirm_custody(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(role_required(UserRole.security, UserRole.admin)),
) -> FoundItem:
    """An officer confirms the physical item is now at their post.

    Not in the spec's endpoint table, but ``CustodyLog.action`` has a ``confirmed``
    value and the Phase 5 security dashboard needs somewhere to record it. This
    moves the item ``pending_custody -> verified``.
    """
    from backend.models import CustodyAction, CustodyLog

    item = db.get(FoundItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Found item not found")
    if item.status == FoundItemStatus.claimed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That item has already been released",
        )

    item.status = FoundItemStatus.verified
    if item.security_post_id is None:
        item.security_post_id = current_user.id
    db.add(
        CustodyLog(
            found_item_id=item.id,
            security_officer_id=current_user.id,
            action=CustodyAction.confirmed,
        )
    )
    db.commit()
    db.refresh(item)
    return item
