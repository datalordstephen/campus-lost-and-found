"""Pydantic request/response schemas.

Rule of thumb: response models never carry ``hashed_password`` or
``private_descriptor``. Those two fields exist only server-side.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from backend.models import ClaimStatus, CustodyAction, FoundItemStatus, LostItemStatus, UserRole

ORM = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- #
# Auth / users
# --------------------------------------------------------------------------- #
class UserCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    # bcrypt silently truncates past 72 bytes, so cap it here instead.
    password: str = Field(min_length=8, max_length=72)
    role: UserRole = UserRole.student


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ORM

    id: int
    full_name: str
    email: EmailStr
    role: UserRole
    incentive_credits: int
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class TokenPayload(BaseModel):
    """Decoded JWT body."""

    sub: str
    role: UserRole
    exp: int


# --------------------------------------------------------------------------- #
# Found items
# --------------------------------------------------------------------------- #
class FoundItemCreate(BaseModel):
    """Sent as multipart/form-data alongside the image file."""

    location: str = Field(min_length=1, max_length=255)
    security_post_id: int | None = None
    description: str | None = Field(default=None, max_length=1000)


class FoundItemOut(BaseModel):
    model_config = ORM

    id: int
    image_path: str
    description: str | None
    location: str
    submitted_by: int
    security_post_id: int | None
    embedding_id: int | None
    status: FoundItemStatus
    created_at: datetime


# --------------------------------------------------------------------------- #
# Lost items
# --------------------------------------------------------------------------- #
class LostItemCreate(BaseModel):
    """Sent as multipart/form-data; the image is optional."""

    description: str = Field(min_length=1, max_length=1000)
    location_last_seen: str = Field(min_length=1, max_length=255)
    # A detail only the true owner would know (scratch, sticker, lock-screen
    # photo). Stored encrypted and used as the NLI premise at claim time.
    private_descriptor: str = Field(min_length=1, max_length=1000)


class LostItemOut(BaseModel):
    model_config = ORM

    id: int
    description: str
    image_path: str | None
    location_last_seen: str
    reported_by: int
    embedding_id: int | None
    status: LostItemStatus
    created_at: datetime


# --------------------------------------------------------------------------- #
# Matching
# --------------------------------------------------------------------------- #
class FoundItemMatch(BaseModel):
    """A found item retrieved as a candidate for some lost item."""

    score: float
    item: FoundItemOut


class LostItemMatch(BaseModel):
    """A lost item retrieved as a candidate for some found item."""

    score: float
    item: LostItemOut


# --------------------------------------------------------------------------- #
# Claims
# --------------------------------------------------------------------------- #
class ClaimCreate(BaseModel):
    lost_item_id: int
    found_item_id: int
    claimant_description: str = Field(min_length=1, max_length=2000)


class ClaimOut(BaseModel):
    model_config = ORM

    id: int
    lost_item_id: int
    found_item_id: int
    claimant_id: int
    claimant_description: str
    nli_score: float | None
    status: ClaimStatus
    created_at: datetime


class ClaimVerifyResult(BaseModel):
    claim_id: int
    nli_score: float
    threshold: float
    status: ClaimStatus


class ClaimReceipt(BaseModel):
    """What the *claimant* is told.

    Deliberately omits ``nli_score``. Handing the raw entailment probability back
    to whoever submitted the text turns verification into a hill-climbing game:
    tweak the wording, watch the number move, repeat until it clears 0.7.
    Staff read the score through ``ClaimOut``; claimants get the verdict only.
    """

    id: int
    lost_item_id: int
    found_item_id: int
    claimant_id: int
    status: ClaimStatus
    attempts_used: int
    attempts_remaining: int
    created_at: datetime


class CustodyLogOut(BaseModel):
    model_config = ORM

    id: int
    found_item_id: int
    security_officer_id: int
    action: CustodyAction
    timestamp: datetime


# --------------------------------------------------------------------------- #
# Admin
# --------------------------------------------------------------------------- #
class SystemStats(BaseModel):
    total_users: int
    users_by_role: dict[str, int]
    total_found_items: int
    total_lost_items: int
    total_claims: int
    claims_released: int
    faiss_vectors: int


class Message(BaseModel):
    detail: str


# --------------------------------------------------------------------------- #
# Submission results — the POST endpoints return the new row *and* the matches
# the system found for it, so the dashboard needs only one round trip.
# --------------------------------------------------------------------------- #
class FoundItemSubmitResult(BaseModel):
    item: FoundItemOut
    matches: list["LostItemMatch"]


class LostItemSubmitResult(BaseModel):
    item: LostItemOut
    matches: list["FoundItemMatch"]
