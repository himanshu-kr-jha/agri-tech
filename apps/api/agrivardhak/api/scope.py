"""ContextScope — the single enforcement point for the information boundary (INV-5).

The farmer↔FPO boundary is enforced by *data*, not by prompts. A farmer's assistant context
cannot contain another farmer's row because the query never returned it. There is no prompt
instruction to bypass, no jailbreak that helps, and no model behaviour to rely on.

Every repository takes a ContextScope and applies its filter in SQL. The assistants retrieve
through the same repositories, so FR-809 holds for the UI and the LLM identically.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import ColumnElement

from agrivardhak.domain.enums import Role, VisibilityScope


class ScopeViolation(PermissionError):
    """Raised when a caller asks for something their scope does not cover.

    Deliberately an error rather than an empty result: silently returning nothing hides
    authorization bugs, and a farmer seeing a blank screen cannot tell the difference
    between "no data" and "we broke it".
    """


@dataclass(frozen=True)
class ContextScope:
    """Who is asking, on behalf of which organization, about whom.

    Construct via :func:`for_user`; do not build one from a client-supplied ``org_id``
    (NFR-402) — the organization must come from the verified token, or the boundary is
    decorative.
    """

    actor_user_id: uuid.UUID
    roles: frozenset[Role]
    organization_id: uuid.UUID | None = None
    #: Set when the actor is a farmer. Their own data is the whole of their world.
    farmer_id: uuid.UUID | None = None
    #: Optional narrowing, e.g. a field officer's assigned farmers. Empty means "no extra
    #: narrowing", not "nothing".
    subject_farmer_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)

    # ----------------------------------------------------------------- role predicates

    @property
    def is_platform_admin(self) -> bool:
        return Role.PLATFORM_ADMIN in self.roles

    @property
    def is_org_staff(self) -> bool:
        return bool(
            self.roles
            & {
                Role.FPO_CEO,
                Role.FIELD_OFFICER,
                Role.MARKET_OFFICER,
                Role.FINANCE_OFFICER,
            }
        )

    @property
    def is_farmer(self) -> bool:
        return Role.FARMER in self.roles and self.farmer_id is not None

    @property
    def audience(self) -> str:
        """Which assistant context this scope produces (packet.PacketScope.audience)."""
        return "FPO" if (self.is_org_staff or self.is_platform_admin) else "FARMER"

    # ----------------------------------------------------------------- visibility

    def visible_scopes(self) -> frozenset[VisibilityScope]:
        """Which visibility levels this actor may read.

        The critical line is that a farmer never gets ``ORG_INTERNAL`` — not even for rows
        that are *about them*. Buyer negotiation state concerning a farmer's own lot is
        still organization-internal until the organization shares it (context.md §4).
        """
        if self.is_platform_admin:
            return frozenset(VisibilityScope)
        if self.is_org_staff:
            return frozenset(VisibilityScope)
        return frozenset(
            {
                VisibilityScope.OWNER,
                VisibilityScope.SHARED_WITH_MEMBERS,
                VisibilityScope.PUBLIC,
            }
        )

    def visibility_filter(self, visibility_column: ColumnElement[Any]) -> ColumnElement[Any]:
        """SQL predicate restricting a table's ``visibility`` column to this scope."""
        return visibility_column.in_(list(self.visible_scopes()))

    def farmer_filter(self, farmer_id_column: ColumnElement[Any]) -> ColumnElement[Any] | None:
        """SQL predicate restricting rows to the farmers this actor may see.

        Returns ``None`` when no narrowing applies (admin, or org staff with full access),
        which callers must treat as "no additional WHERE clause" rather than as "match none".
        """
        if self.is_platform_admin:
            return None
        if self.is_farmer:
            # A farmer sees exactly one farmer: themselves.
            return farmer_id_column == self.farmer_id
        if self.subject_farmer_ids:
            return farmer_id_column.in_(list(self.subject_farmer_ids))
        return None

    def org_filter(self, org_id_column: ColumnElement[Any]) -> ColumnElement[Any] | None:
        if self.is_platform_admin:
            return None
        if self.organization_id is None:
            raise ScopeViolation("scope has no organization and the actor is not a platform admin")
        return org_id_column == self.organization_id

    # ----------------------------------------------------------------- assertions

    def require_org(self) -> uuid.UUID:
        if self.organization_id is None:
            raise ScopeViolation("this operation requires an organization scope")
        return self.organization_id

    def require_any_role(self, *roles: Role) -> None:
        if self.is_platform_admin:
            return
        if not (self.roles & set(roles)):
            raise ScopeViolation(
                f"requires one of {sorted(r.value for r in roles)}; "
                f"actor holds {sorted(r.value for r in self.roles)}"
            )

    def can_see_farmer(self, farmer_id: uuid.UUID) -> bool:
        if self.is_platform_admin or self.is_org_staff:
            return True
        if self.is_farmer:
            return farmer_id == self.farmer_id
        return False

    def require_farmer_access(self, farmer_id: uuid.UUID) -> None:
        if not self.can_see_farmer(farmer_id):
            raise ScopeViolation("actor may not access this farmer")


def for_user(
    *,
    user_id: uuid.UUID,
    roles: frozenset[Role] | set[Role],
    organization_id: uuid.UUID | None,
    farmer_id: uuid.UUID | None = None,
    subject_farmer_ids: frozenset[uuid.UUID] | None = None,
) -> ContextScope:
    """Build a scope from verified token claims."""
    return ContextScope(
        actor_user_id=user_id,
        roles=frozenset(roles),
        organization_id=organization_id,
        farmer_id=farmer_id,
        subject_farmer_ids=subject_farmer_ids or frozenset(),
    )
