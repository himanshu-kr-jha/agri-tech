"""Scoped repository base.

Every read goes through a repository that takes a :class:`ContextScope` and applies its
filter in SQL. This is where INV-5 is actually enforced: not in the UI, not in a prompt,
but in the WHERE clause.

Subclasses declare how their table relates to an organization and to a farmer, and the base
does the rest. That keeps the boundary from depending on each new endpoint remembering to
apply it.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from agrivardhak.api.scope import ContextScope, ScopeViolation
from agrivardhak.db.base import Base


class ScopedRepository[TModel: Base]:
    """Base for every repository that reads scoped data.

    Subclasses set:

    * ``model`` — the ORM class
    * ``org_column`` — attribute name holding ``organization_id``, or ``None``
    * ``farmer_column`` — attribute name holding ``farmer_id``, or ``None``
    * ``visibility_column`` — attribute name holding a ``VisibilityScope``, or ``None``

    A table with none of the three is unscoped reference data (crops, varieties, schemes)
    and must say so explicitly by leaving all three ``None`` — so that an unscoped table is
    a deliberate choice rather than an oversight.
    """

    model: type[TModel]
    org_column: str | None = "organization_id"
    farmer_column: str | None = None
    visibility_column: str | None = None

    def __init__(self, session: Session, scope: ContextScope) -> None:
        self.session = session
        self.scope = scope

    # ----------------------------------------------------------------- query building

    def _base_select(self) -> Select[tuple[TModel]]:
        stmt = select(self.model)
        return self._apply_scope(stmt)

    def _apply_scope(self, stmt: Select[Any]) -> Select[Any]:
        if self.org_column:
            column = getattr(self.model, self.org_column)
            predicate = self.scope.org_filter(column)
            if predicate is not None:
                stmt = stmt.where(predicate)

        if self.farmer_column:
            column = getattr(self.model, self.farmer_column)
            predicate = self.scope.farmer_filter(column)
            if predicate is not None:
                stmt = stmt.where(predicate)

        if self.visibility_column:
            column = getattr(self.model, self.visibility_column)
            stmt = stmt.where(self.scope.visibility_filter(column))

        return stmt

    # ----------------------------------------------------------------- reads

    def get(self, entity_id: uuid.UUID) -> TModel | None:
        """Fetch by id **within scope**.

        Note this returns ``None`` for a row that exists but is out of scope, rather than
        raising — so an out-of-scope id is indistinguishable from a missing one and we do
        not leak existence. Callers that need the distinction for their own data should
        assert access via the scope first.
        """
        stmt = self._base_select().where(self.model.id == entity_id)  # type: ignore[attr-defined]
        return self.session.execute(stmt).scalar_one_or_none()

    def get_or_raise(self, entity_id: uuid.UUID) -> TModel:
        found = self.get(entity_id)
        if found is None:
            raise ScopeViolation(f"{self.model.__name__} {entity_id} not found in scope")
        return found

    def list(self, *, limit: int = 100, offset: int = 0) -> list[TModel]:
        stmt = self._base_select().limit(limit).offset(offset)
        return list(self.session.execute(stmt).scalars())

    def count(self) -> int:
        from sqlalchemy import func

        stmt = self._apply_scope(select(func.count()).select_from(self.model))
        return int(self.session.execute(stmt).scalar_one())

    # ----------------------------------------------------------------- writes

    def add(self, entity: TModel) -> TModel:
        self.session.add(entity)
        self.session.flush()
        return entity
