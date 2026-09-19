"""The public surface (UI-12, ADR-0026).

One endpoint, deliberately: the totals the landing page prints. It is the only route in
the product that answers without a token, alongside ``/health``, ``/auth/demo-accounts``
and ``/translate/version``.

Three properties make that safe, and all three are load-bearing:

* It is **aggregate only**. Counts and a summed area — never a farmer, a plot, a decision
  or an organization name. Nothing here crosses the information boundary (INV-5), because
  nothing here is about an identifiable party.
* It is **platform-wide, not org-scoped**, which is why it needs no ``ContextScope``. The
  org-scoped version of these same counts already exists behind auth in ``dashboard.py``.
* It **says whether the dataset is synthetic**. The landing page states these as claims
  about the model ("farmers modelled"), not about customers, and the API is what makes
  that claim checkable rather than a UI assumption.

The caveat, recorded here because it will matter before it is obvious: the moment a
non-synthetic organization is onboarded, this route begins publishing that organization's
real totals to an anonymous caller. That is adjacent to INV-9 (the farmer owns their
data). Before any real org lands, this must either aggregate only over ``is_synthetic``
rows or move behind an explicit per-organization opt-in. See ADR-0026.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agrivardhak.db.session import get_session
from agrivardhak.domain.models.crops import CropCycle
from agrivardhak.domain.models.land import Plot
from agrivardhak.domain.models.organization import Farmer, Organization
from agrivardhak.domain.units import sqm_to_acres

router = APIRouter(prefix="/api/v1/public", tags=["public"])

SessionDep = Annotated[Session, Depends(get_session)]


class PlatformStats(BaseModel):
    """What the landing page's three tiles print, plus the honesty flag.

    Field names carry the verb the UI uses. That is not decoration: "farmers modelled" is
    a true statement about a dataset, where "farmers" alone reads as a customer count, and
    keeping the verb in the contract stops the distinction being lost at the edge.
    """

    farmers_modelled: int = Field(description="Farmer rows the platform holds.")
    crop_cycles_analysed: int = Field(description="Crop cycle rows across all seasons.")
    acres_mapped: int = Field(
        description="Whole acres, converted here from canonical square metres (ADR-0009)."
    )
    organizations: int = Field(description="Collectives on the platform, of any type.")
    is_synthetic: bool = Field(
        description="True while every organization on the platform is seeded demo data."
    )
    generated_at: dt.datetime


@router.get("/platform-stats", response_model=PlatformStats)
def platform_stats(session: SessionDep) -> PlatformStats:
    """Platform-wide totals. No authentication, by design — see the module docstring.

    Note the absent ``scope: CurrentScope``. That omission *is* the mechanism: a route
    without the dependency is never asked for a bearer token, and a caller who sends a
    garbage one is ignored rather than refused. There is no optional-auth branch here to
    get wrong.
    """
    farmers = session.execute(select(func.count()).select_from(Farmer)).scalar_one()
    crop_cycles = session.execute(select(func.count()).select_from(CropCycle)).scalar_one()
    organizations = session.execute(select(func.count()).select_from(Organization)).scalar_one()

    # Area is stored in square metres and converted at the edge (ADR-0009). The edge is
    # here rather than in the web tier, because the web tier does no unit arithmetic —
    # a React component that divides by 4046.86 is how acres and hectares get mixed up.
    area_sqm = session.execute(
        select(func.coalesce(func.sum(Plot.area_sqm), 0)).select_from(Plot)
    ).scalar_one()

    # Truncate rather than round: 2,412.8 acres mapped is a claim about 2,412 whole acres
    # we can point at, and rounding up invents land.
    acres = int(sqm_to_acres(area_sqm))

    real_organizations = session.execute(
        select(func.count()).select_from(Organization).where(Organization.is_synthetic.is_(False))
    ).scalar_one()

    return PlatformStats(
        farmers_modelled=farmers,
        crop_cycles_analysed=crop_cycles,
        acres_mapped=acres,
        organizations=organizations,
        is_synthetic=real_organizations == 0,
        generated_at=dt.datetime.now(dt.UTC),
    )
