"""The claim flow: initiate -> NLI verify -> security release -> incentive credit.

This is the security-critical path. CLIP gets a student to a shortlist of items
that *look* like theirs; nothing about a photograph distinguishes two identical
black umbrellas. The private descriptor recorded at report time is what actually
establishes ownership, and this router is where it gets checked.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend import faiss_store, verification
from backend.auth import decrypt_text, role_required
from backend.database import get_db
from backend.models import (
    Claim,
    ClaimStatus,
    CustodyAction,
    CustodyLog,
    FoundItem,
    FoundItemStatus,
    LostItem,
    LostItemStatus,
    User,
    UserRole,
)
from backend.schemas import ClaimCreate, ClaimOut, ClaimReceipt, ClaimVerifyResult

load_dotenv()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/claims", tags=["claims"])

# A claimant who can retry indefinitely and watch the verdict flip will
# eventually word their way past the threshold. Cap the attempts per item.
MAX_ATTEMPTS_PER_ITEM = int(os.getenv("MAX_CLAIM_ATTEMPTS", "3"))


def _attempts_used(db: Session, claimant_id: int, found_item_id: int) -> int:
    return int(
        db.scalar(
            select(func.count(Claim.id)).where(
                Claim.claimant_id == claimant_id,
                Claim.found_item_id == found_item_id,
            )
        )
        or 0
    )


def _receipt(db: Session, claim: Claim) -> ClaimReceipt:
    used = _attempts_used(db, claim.claimant_id, claim.found_item_id)
    return ClaimReceipt(
        id=claim.id,
        lost_item_id=claim.lost_item_id,
        found_item_id=claim.found_item_id,
        claimant_id=claim.claimant_id,
        status=claim.status,
        attempts_used=used,
        attempts_remaining=max(0, MAX_ATTEMPTS_PER_ITEM - used),
        created_at=claim.created_at,
    )


def _run_verification(db: Session, claim: Claim) -> float:
    """Score the claim against the stored descriptor and set its status."""
    lost_item = db.get(LostItem, claim.lost_item_id)
    if lost_item is None or not lost_item.private_descriptor:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The lost item report has no private descriptor to verify against",
        )

    # Plaintext exists only inside this call — it is never logged or returned.
    descriptor = decrypt_text(lost_item.private_descriptor)
    try:
        score = verification.verify_claim(descriptor, claim.claimant_description)
    except Exception as exc:
        logger.exception("NLI verification unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ownership verification is temporarily unavailable; please try again later",
        ) from exc

    claim.nli_score = score
    claim.status = ClaimStatus.approved if verification.passes(score) else ClaimStatus.rejected
    if claim.status == ClaimStatus.approved:
        lost_item.status = LostItemStatus.matched
    db.commit()
    db.refresh(claim)

    logger.info(
        "Claim %s on found item %s: entailment %.4f -> %s",
        claim.id,
        claim.found_item_id,
        score,
        claim.status.value,
    )
    return score


# --------------------------------------------------------------------------- #
# POST /claims/  — initiate
# --------------------------------------------------------------------------- #
@router.post("/", response_model=ClaimReceipt, status_code=status.HTTP_201_CREATED)
def initiate_claim(
    payload: ClaimCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(role_required(UserRole.student, UserRole.security)),
) -> ClaimReceipt:
    """Claim a found item, verifying ownership against the stored private detail."""
    lost_item = db.get(LostItem, payload.lost_item_id)
    found_item = db.get(FoundItem, payload.found_item_id)
    if lost_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lost item not found")
    if found_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Found item not found")

    if lost_item.reported_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only claim against your own lost item report",
        )
    if found_item.status == FoundItemStatus.claimed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That item has already been released to someone else",
        )

    used = _attempts_used(db, current_user.id, payload.found_item_id)
    if used >= MAX_ATTEMPTS_PER_ITEM:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"You have used all {MAX_ATTEMPTS_PER_ITEM} verification attempts for this "
                "item. Please visit the security post in person."
            ),
        )
    # An approved claim is already waiting on a security officer; another
    # attempt would only muddy the queue.
    already_approved = db.scalar(
        select(Claim).where(
            Claim.claimant_id == current_user.id,
            Claim.found_item_id == payload.found_item_id,
            Claim.status.in_([ClaimStatus.approved, ClaimStatus.released]),
        )
    )
    if already_approved is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have an approved claim on this item",
        )

    claim = Claim(
        lost_item_id=payload.lost_item_id,
        found_item_id=payload.found_item_id,
        claimant_id=current_user.id,
        claimant_description=payload.claimant_description,
        status=ClaimStatus.pending,
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)

    _run_verification(db, claim)
    return _receipt(db, claim)


# --------------------------------------------------------------------------- #
# POST /claims/{id}/verify  — re-run scoring
# --------------------------------------------------------------------------- #
@router.post("/{claim_id}/verify", response_model=ClaimVerifyResult)
def verify_claim_endpoint(
    claim_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(role_required(UserRole.security, UserRole.admin)),
) -> ClaimVerifyResult:
    """Re-score a claim. Staff only — the result includes the raw entailment score.

    ``POST /claims/`` already verifies on submission; this exists so an officer
    can re-run scoring after a model or threshold change without asking the
    student to resubmit.
    """
    claim = db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")
    if claim.status == ClaimStatus.released:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This claim has already been released and cannot be re-verified",
        )

    score = _run_verification(db, claim)
    return ClaimVerifyResult(
        claim_id=claim.id,
        nli_score=score,
        threshold=verification.ENTAILMENT_THRESHOLD,
        status=claim.status,
    )


# --------------------------------------------------------------------------- #
# POST /claims/{id}/release  — hand the item over
# --------------------------------------------------------------------------- #
@router.post("/{claim_id}/release", response_model=ClaimOut)
def release_claim(
    claim_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(role_required(UserRole.security, UserRole.admin)),
) -> Claim:
    """Release the item to the claimant and credit whoever handed it in."""
    claim = db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")
    if claim.status == ClaimStatus.released:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Item already released"
        )
    if claim.status != ClaimStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only approved claims can be released; this one is '{claim.status.value}'",
        )

    found_item = db.get(FoundItem, claim.found_item_id)
    lost_item = db.get(LostItem, claim.lost_item_id)

    claim.status = ClaimStatus.released
    found_item.status = FoundItemStatus.claimed
    if lost_item is not None:
        lost_item.status = LostItemStatus.claimed

    db.add(
        CustodyLog(
            found_item_id=found_item.id,
            security_officer_id=current_user.id,
            action=CustodyAction.released,
        )
    )

    # The incentive: the student who handed the item in earns a credit.
    finder = db.get(User, found_item.submitted_by)
    if finder is not None and finder.id != claim.claimant_id:
        finder.incentive_credits += 1

    db.commit()
    db.refresh(claim)

    # Out of circulation — drop both vectors so they stop surfacing as matches.
    for kind, item in ((faiss_store.FOUND, found_item), (faiss_store.LOST, lost_item)):
        if item is not None and item.embedding_id is not None:
            faiss_store.remove_embedding(kind, item.embedding_id)
    faiss_store.save_index()

    logger.info(
        "Claim %s released by officer %s; credited user %s",
        claim.id,
        current_user.id,
        found_item.submitted_by,
    )
    return claim


# --------------------------------------------------------------------------- #
# Listings
# --------------------------------------------------------------------------- #
@router.get("/", response_model=list[ClaimOut])
def list_claims(
    claim_status: ClaimStatus | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(role_required(UserRole.security, UserRole.admin)),
) -> list[Claim]:
    """The security queue. Includes ``nli_score`` — staff only."""
    query = select(Claim).order_by(Claim.created_at.desc())
    if claim_status is not None:
        query = query.where(Claim.status == claim_status)
    return list(db.scalars(query.limit(limit).offset(offset)).all())


@router.get("/mine", response_model=list[ClaimReceipt])
def list_my_claims(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        role_required(UserRole.student, UserRole.security, UserRole.admin)
    ),
) -> list[ClaimReceipt]:
    claims = db.scalars(
        select(Claim)
        .where(Claim.claimant_id == current_user.id)
        .order_by(Claim.created_at.desc())
    ).all()
    return [_receipt(db, claim) for claim in claims]
