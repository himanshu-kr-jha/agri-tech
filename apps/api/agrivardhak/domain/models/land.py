"""Farm, Plot, PlotTenure — and the resource graph for integrated farming.

ADR-0003 is the load-bearing decision here: land ownership, cultivation responsibility and
organization membership are three separate relationships. ``plot.farmer_id`` does not exist.
"""

from __future__ import annotations

import datetime as dt
import uuid

from geoalchemy2 import Geography
from sqlalchemy import Date, Enum, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agrivardhak.db.base import Base, Json, ShortText, Sqm, TimestampMixin, UuidPk
from agrivardhak.domain import enums


class Farm(Base, TimestampMixin):
    """An operational grouping of plots run by one operator.

    ``operator_farmer_id`` is who actually runs the farm day to day — which may be nobody
    who holds tenure on its plots (a tenant cultivator, a family member). Keeping it
    separate from tenure is what makes that representable.
    """

    __tablename__ = "farm"

    id: Mapped[UuidPk]
    operator_farmer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farmer.id"), nullable=False)
    label: Mapped[ShortText] = mapped_column(nullable=False)
    village: Mapped[str | None] = mapped_column(String(160))

    plots: Mapped[list[Plot]] = relationship(back_populates="farm")
    resources: Mapped[list[FarmResource]] = relationship(back_populates="farm")


class Plot(Base, TimestampMixin):
    """The atomic unit of cultivation.

    ``area_sqm`` here is the working value. When sources disagree about it the truth lives
    in ``Observation`` rows and a ``DataDiscrepancy`` — this column is a convenience, and
    anything making a decision on plot area must go through the provenance layer (INV-3).
    """

    __tablename__ = "plot"
    __table_args__ = (Index("ix_plot_farm", "farm_id"),)

    id: Mapped[UuidPk]
    farm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farm.id"), nullable=False)
    label: Mapped[ShortText] = mapped_column(nullable=False)
    registration_no: Mapped[str | None] = mapped_column(String(120))

    area_sqm: Mapped[Sqm] = mapped_column(nullable=False)
    boundary: Mapped[str | None] = mapped_column(Geography("POLYGON", srid=4326))
    centroid: Mapped[str | None] = mapped_column(Geography("POINT", srid=4326))

    soil_type: Mapped[str | None] = mapped_column(String(80))
    irrigation_source: Mapped[str | None] = mapped_column(String(80))

    farm: Mapped[Farm] = relationship(back_populates="plots")
    tenures: Mapped[list[PlotTenure]] = relationship(back_populates="plot")
    crop_cycles: Mapped[list[CropCycle]] = relationship(back_populates="plot")


class PlotTenure(Base, TimestampMixin):
    """Who holds a plot, how, for what share, over what period.

    Active shares on a plot should sum to 100%. When they do not, the system raises a
    ``DataDiscrepancy`` rather than rejecting the write — real land records are messy, and
    refusing the write destroys information we need (ADR-0003).
    """

    __tablename__ = "plot_tenure"
    __table_args__ = (Index("ix_plot_tenure_plot_valid", "plot_id", "valid_from", "valid_to"),)

    id: Mapped[UuidPk]
    plot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plot.id"), nullable=False)
    holder_farmer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farmer.id"), nullable=False)
    tenure_type: Mapped[enums.TenureType] = mapped_column(
        Enum(enums.TenureType, name="tenure_type"), nullable=False
    )
    share_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=100)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date)
    evidence_ref: Mapped[str | None] = mapped_column(Text)

    plot: Mapped[Plot] = relationship(back_populates="tenures")


class FarmResource(Base, TimestampMixin):
    """Integrated farming as one typed entity rather than six subsystems (Q5).

    Six independent subsystems would have tripled the schema and none would have been deep
    enough to matter. One typed resource plus a flow edge captures everything discovery
    asked for and leaves substitution reasoning (FR-208) as a stretch goal needing no
    schema change.
    """

    __tablename__ = "farm_resource"

    id: Mapped[UuidPk]
    farm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farm.id"), nullable=False)
    plot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("plot.id"))
    type: Mapped[enums.FarmResourceType] = mapped_column(
        Enum(enums.FarmResourceType, name="farm_resource_type"), nullable=False
    )
    label: Mapped[ShortText] = mapped_column(nullable=False)
    quantity: Mapped[float | None]
    unit: Mapped[str | None] = mapped_column(String(32))
    attributes: Mapped[Json | None]
    active_from: Mapped[dt.date | None] = mapped_column(Date)
    active_to: Mapped[dt.date | None] = mapped_column(Date)

    farm: Mapped[Farm] = relationship(back_populates="resources")


class ResourceFlow(Base, TimestampMixin):
    """A directed edge between two farm resources.

    Makes the classic cycles expressible as data:
        livestock --FERTILITY--> manure --FERTILITY--> crop --RESIDUE--> livestock
    """

    __tablename__ = "resource_flow"

    id: Mapped[UuidPk]
    from_resource_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farm_resource.id"), nullable=False
    )
    to_resource_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farm_resource.id"), nullable=False
    )
    flow_type: Mapped[enums.ResourceFlowType] = mapped_column(
        Enum(enums.ResourceFlowType, name="resource_flow_type"), nullable=False
    )
    quantity_per_cycle: Mapped[float | None]
    unit: Mapped[str | None] = mapped_column(String(32))
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))


# Imported late to avoid a circular import at module load; CropCycle lives in crops.py.
from agrivardhak.domain.models.crops import CropCycle  # noqa: E402
