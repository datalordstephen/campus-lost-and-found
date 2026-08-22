"""SQLAlchemy ORM models for the campus lost & found system."""

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum as SQLEnum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum_col(enum_cls: type[enum.Enum], **kwargs):
    """Store the enum *value* ("student") rather than the member name."""
    return SQLEnum(
        enum_cls,
        values_callable=lambda e: [m.value for m in e],
        native_enum=False,
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class UserRole(str, enum.Enum):
    student = "student"
    security = "security"
    admin = "admin"


class FoundItemStatus(str, enum.Enum):
    pending_custody = "pending_custody"
    verified = "verified"
    claimed = "claimed"


class LostItemStatus(str, enum.Enum):
    open = "open"
    matched = "matched"
    claimed = "claimed"


class ClaimStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    released = "released"


class CustodyAction(str, enum.Enum):
    confirmed = "confirmed"
    released = "released"


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        _enum_col(UserRole, name="user_role"), default=UserRole.student, nullable=False
    )
    incentive_credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    found_items: Mapped[list["FoundItem"]] = relationship(
        back_populates="submitter",
        foreign_keys="FoundItem.submitted_by",
    )
    guarded_items: Mapped[list["FoundItem"]] = relationship(
        back_populates="security_post",
        foreign_keys="FoundItem.security_post_id",
    )
    lost_items: Mapped[list["LostItem"]] = relationship(back_populates="reporter")
    claims: Mapped[list["Claim"]] = relationship(back_populates="claimant")


class FoundItem(Base):
    __tablename__ = "found_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    image_path: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    security_post_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    # Position of this item's vector inside the FAISS index; NULL until encoded.
    embedding_id: Mapped[int | None] = mapped_column(Integer, unique=True, index=True, nullable=True)
    status: Mapped[FoundItemStatus] = mapped_column(
        _enum_col(FoundItemStatus, name="found_item_status"),
        default=FoundItemStatus.pending_custody,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    submitter: Mapped["User"] = relationship(
        back_populates="found_items", foreign_keys=[submitted_by]
    )
    security_post: Mapped["User | None"] = relationship(
        back_populates="guarded_items", foreign_keys=[security_post_id]
    )
    claims: Mapped[list["Claim"]] = relationship(back_populates="found_item")
    custody_logs: Mapped[list["CustodyLog"]] = relationship(back_populates="found_item")


class LostItem(Base):
    __tablename__ = "lost_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Fernet ciphertext — never returned to any client. Decrypted only inside
    # verification.py when scoring a claim.
    private_descriptor: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    location_last_seen: Mapped[str] = mapped_column(String(255), nullable=False)
    reported_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    embedding_id: Mapped[int | None] = mapped_column(Integer, unique=True, index=True, nullable=True)
    status: Mapped[LostItemStatus] = mapped_column(
        _enum_col(LostItemStatus, name="lost_item_status"),
        default=LostItemStatus.open,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    reporter: Mapped["User"] = relationship(back_populates="lost_items")
    claims: Mapped[list["Claim"]] = relationship(back_populates="lost_item")


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lost_item_id: Mapped[int] = mapped_column(
        ForeignKey("lost_items.id"), nullable=False, index=True
    )
    found_item_id: Mapped[int] = mapped_column(
        ForeignKey("found_items.id"), nullable=False, index=True
    )
    claimant_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    claimant_description: Mapped[str] = mapped_column(String(2000), nullable=False)
    nli_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[ClaimStatus] = mapped_column(
        _enum_col(ClaimStatus, name="claim_status"), default=ClaimStatus.pending, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    lost_item: Mapped["LostItem"] = relationship(back_populates="claims")
    found_item: Mapped["FoundItem"] = relationship(back_populates="claims")
    claimant: Mapped["User"] = relationship(back_populates="claims")


class CustodyLog(Base):
    __tablename__ = "custody_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    found_item_id: Mapped[int] = mapped_column(
        ForeignKey("found_items.id"), nullable=False, index=True
    )
    security_officer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    action: Mapped[CustodyAction] = mapped_column(
        _enum_col(CustodyAction, name="custody_action"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    found_item: Mapped["FoundItem"] = relationship(back_populates="custody_logs")
    security_officer: Mapped["User"] = relationship()
