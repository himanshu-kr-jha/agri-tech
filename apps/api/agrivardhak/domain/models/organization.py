"""Organization, membership, people and roles.

ADR-0002: one Organization abstraction discriminated by type, so PACS/SHG support later
is a type value plus a governance profile — not a migration across every table.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agrivardhak.db.base import (
    Base,
    Json,
    Paise,
    ShortText,
    TimestampMixin,
    UuidPk,
)
from agrivardhak.domain import enums


class Organization(Base, TimestampMixin):
    __tablename__ = "organization"

    id: Mapped[UuidPk]
    type: Mapped[enums.OrganizationType] = mapped_column(
        Enum(enums.OrganizationType, name="organization_type"), nullable=False
    )
    name: Mapped[ShortText] = mapped_column(nullable=False)
    legal_form: Mapped[str | None] = mapped_column(String(120))
    registration_no: Mapped[str | None] = mapped_column(String(120))

    district: Mapped[ShortText] = mapped_column(nullable=False)
    state: Mapped[ShortText] = mapped_column(nullable=False)

    #: True when this organization is demo data and must carry the DEMO DATA marker (UI-04).
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    memberships: Mapped[list[Membership]] = relationship(back_populates="organization")
    resources: Mapped[list[OrgResource]] = relationship(back_populates="organization")


class GovernanceProfile(Base, TimestampMixin):
    """Type-specific governance rules, kept out of branching logic in the modules."""

    __tablename__ = "governance_profile"

    id: Mapped[UuidPk]
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organization.id"), nullable=False, unique=True
    )
    board_size: Mapped[int | None] = mapped_column(Integer)
    approval_rules: Mapped[Json | None]
    notes: Mapped[str | None] = mapped_column(Text)


class OrgResource(Base, TimestampMixin):
    """FR-103.

    ``quantity`` is nullable on purpose: an organization that has not told us its cold-store
    capacity is *unknown*, not zero. The orchestrator must be able to tell the difference,
    because planning against an assumed zero silently drops a real option.
    """

    __tablename__ = "org_resource"

    id: Mapped[UuidPk]
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organization.id"), nullable=False
    )
    type: Mapped[enums.OrgResourceType] = mapped_column(
        Enum(enums.OrgResourceType, name="org_resource_type"), nullable=False
    )
    label: Mapped[ShortText] = mapped_column(nullable=False)
    quantity: Mapped[float | None]
    unit: Mapped[str | None] = mapped_column(String(32))
    value_paise: Mapped[Paise | None]
    attributes: Mapped[Json | None]

    organization: Mapped[Organization] = relationship(back_populates="resources")


class User(Base, TimestampMixin):
    __tablename__ = "app_user"

    id: Mapped[UuidPk]
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    display_name: Mapped[ShortText] = mapped_column(nullable=False)
    #: BCP-47; drives assistant response language (FR-812).
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="hi-IN")
    #: Set when this user *is* a farmer, so the farmer context scope can resolve.
    farmer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("farmer.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    role_grants: Mapped[list[RoleGrant]] = relationship(back_populates="user")


class RoleGrant(Base, TimestampMixin):
    """FR-104: a person may hold several roles; permissions are the union of grants."""

    __tablename__ = "role_grant"
    __table_args__ = (UniqueConstraint("user_id", "organization_id", "role", name="user_org_role"),)

    id: Mapped[UuidPk]
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    #: Null for platform-wide roles such as PLATFORM_ADMIN.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organization.id"))
    role: Mapped[enums.Role] = mapped_column(Enum(enums.Role, name="role"), nullable=False)

    user: Mapped[User] = relationship(back_populates="role_grants")


class Farmer(Base, TimestampMixin):
    """FR-201.

    Only stable, low-decision-impact attributes are columns here. Volatile facts —
    water availability, livestock counts, landholding under dispute — live in
    ``Observation`` so they carry provenance (ADR-0005).
    """

    __tablename__ = "farmer"

    id: Mapped[UuidPk]
    full_name: Mapped[ShortText] = mapped_column(nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="hi-IN")

    village: Mapped[str | None] = mapped_column(String(160))
    block: Mapped[str | None] = mapped_column(String(160))
    district: Mapped[ShortText] = mapped_column(nullable=False)
    state: Mapped[ShortText] = mapped_column(nullable=False)
    #: Prayagraj tract: GANGA_PAR | DOAB | YAMUNA_PAR (docs/DEMO-CONTEXT.md §2).
    tract: Mapped[str | None] = mapped_column(String(40))

    household_size: Mapped[int | None] = mapped_column(Integer)

    #: Sensitive attributes are consent-gated and used ONLY for scheme eligibility
    #: (FR-566). They must never reach a ranking, scoring or prioritization path.
    category: Mapped[str | None] = mapped_column(String(20))
    is_woman_farmer: Mapped[bool | None] = mapped_column(Boolean)
    has_disability: Mapped[bool | None] = mapped_column(Boolean)

    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    memberships: Mapped[list[Membership]] = relationship(back_populates="farmer")


class Membership(Base, TimestampMixin):
    """A farmer's relationship to an organization.

    DATA-MODEL.md Q2: a join entity from day one, because a farmer is routinely in an FPO
    for produce, a PACS for credit and an SHG for savings. ``farmer.organization_id`` would
    have made that unrepresentable and forced a painful migration later.
    """

    __tablename__ = "membership"
    __table_args__ = (
        UniqueConstraint("farmer_id", "organization_id", name="farmer_org"),
        Index("ix_membership_org_status", "organization_id", "status"),
    )

    id: Mapped[UuidPk]
    farmer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farmer.id"), nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organization.id"), nullable=False
    )
    role: Mapped[enums.MembershipRole] = mapped_column(
        Enum(enums.MembershipRole, name="membership_role"),
        nullable=False,
        default=enums.MembershipRole.MEMBER,
    )
    status: Mapped[enums.MembershipStatus] = mapped_column(
        Enum(enums.MembershipStatus, name="membership_status"),
        nullable=False,
        default=enums.MembershipStatus.ACTIVE,
    )
    joined_at: Mapped[dt.date] = mapped_column(Date, nullable=False)
    left_at: Mapped[dt.date | None] = mapped_column(Date)
    shares_held: Mapped[int | None] = mapped_column(Integer)
    patronage_units: Mapped[float | None]
    #: The MVP UI shows only the primary membership; aggregations always scope by org id
    #: so a multi-org farmer never double-counts.
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    farmer: Mapped[Farmer] = relationship(back_populates="memberships")
    organization: Mapped[Organization] = relationship(back_populates="memberships")


class Announcement(Base, TimestampMixin):
    """FR-105. The only legitimate mechanism for information to cross to farmers (INV-5)."""

    __tablename__ = "announcement"

    id: Mapped[UuidPk]
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organization.id"), nullable=False
    )
    title: Mapped[ShortText] = mapped_column(nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[enums.VisibilityScope] = mapped_column(
        Enum(enums.VisibilityScope, name="visibility_scope"),
        nullable=False,
        default=enums.VisibilityScope.ORG_INTERNAL,
    )
    published_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
