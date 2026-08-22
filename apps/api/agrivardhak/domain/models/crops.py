"""Crop reference data and CropCycle — the central temporal entity of the system.

Nearly every intelligence module joins here: prediction, intervention, harvest, quality and
sale all converge on a crop cycle (DATA-MODEL.md Q4).
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agrivardhak.db.base import (
    Base,
    Json,
    Kg,
    Paise,
    ShortText,
    Sqm,
    TimestampMixin,
    UuidPk,
)
from agrivardhak.domain import enums


class Crop(Base, TimestampMixin):
    __tablename__ = "crop"

    id: Mapped[UuidPk]
    name: Mapped[ShortText] = mapped_column(nullable=False, unique=True)
    name_hi: Mapped[str | None] = mapped_column(String(255))
    default_season: Mapped[enums.Season] = mapped_column(
        Enum(enums.Season, name="season"), nullable=False
    )
    is_perennial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    varieties: Mapped[list[Variety]] = relationship(back_populates="crop")


class Variety(Base, TimestampMixin):
    """Agronomic coefficients live here.

    ``base_yield_kg_per_ha`` and friends must trace to a row in ``seed/sources.md``
    (CLAUDE.md §8 rule 4). ``source_ref`` is not decoration — a variety without one is
    synthetic and must be flagged as such wherever its numbers surface.
    """

    __tablename__ = "variety"
    __table_args__ = (Index("ix_variety_crop", "crop_id"),)

    id: Mapped[UuidPk]
    crop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crop.id"), nullable=False)
    name: Mapped[ShortText] = mapped_column(nullable=False)
    duration_days: Mapped[int | None] = mapped_column(Integer)
    base_yield_kg_per_ha: Mapped[float | None]
    grade_potential: Mapped[enums.Grade | None] = mapped_column(Enum(enums.Grade, name="grade"))
    water_requirement_mm: Mapped[float | None]
    agro_zone: Mapped[str | None] = mapped_column(String(120))
    source_ref: Mapped[str | None] = mapped_column(Text)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    crop: Mapped[Crop] = relationship(back_populates="varieties")


class CropCycle(Base, TimestampMixin):
    """One crop grown on one plot in one season.

    Two cycles on a plot may overlap in time only when both carry ``intercrop_group_id``,
    which models genuine intercropping and relay cropping. An unflagged overlap is a data
    error and raises a discrepancy.

    Expected values are convenience mirrors of the latest ``Prediction``; the authoritative
    record with confidence and evidence is the prediction row, not this column (INV-6).
    """

    __tablename__ = "crop_cycle"
    __table_args__ = (
        Index("ix_crop_cycle_plot_season", "plot_id", "season", "season_year"),
        Index("ix_crop_cycle_status", "status"),
        CheckConstraint("area_sqm > 0", name="area_positive"),
    )

    id: Mapped[UuidPk]
    plot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plot.id"), nullable=False)
    variety_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("variety.id"), nullable=False)

    season: Mapped[enums.Season] = mapped_column(Enum(enums.Season, name="season"), nullable=False)
    season_year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[enums.CropCycleStatus] = mapped_column(
        Enum(enums.CropCycleStatus, name="crop_cycle_status"),
        nullable=False,
        default=enums.CropCycleStatus.PLANNED,
    )

    area_sqm: Mapped[Sqm] = mapped_column(nullable=False)
    sowing_date: Mapped[dt.date | None] = mapped_column(Date)
    expected_harvest_date: Mapped[dt.date | None] = mapped_column(Date)
    actual_harvest_date: Mapped[dt.date | None] = mapped_column(Date)

    farming_method: Mapped[str | None] = mapped_column(String(80))
    #: Set on both cycles when two crops genuinely share the plot in the same window.
    intercrop_group_id: Mapped[uuid.UUID | None]

    expected_yield_kg: Mapped[Kg | None]
    actual_yield_kg: Mapped[Kg | None]
    expected_grade: Mapped[enums.Grade | None] = mapped_column(Enum(enums.Grade, name="grade"))
    actual_grade: Mapped[enums.Grade | None] = mapped_column(Enum(enums.Grade, name="grade"))

    abandoned_reason: Mapped[str | None] = mapped_column(String(120))

    plot: Mapped[Plot] = relationship(back_populates="crop_cycles")
    inputs: Mapped[list[InputApplication]] = relationship(back_populates="crop_cycle")


class InputApplication(Base, TimestampMixin):
    """FR-209. What actually went onto the crop, and what it cost."""

    __tablename__ = "input_application"
    __table_args__ = (Index("ix_input_application_cycle", "crop_cycle_id"),)

    id: Mapped[UuidPk]
    crop_cycle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crop_cycle.id"), nullable=False)
    category: Mapped[enums.InputCategory] = mapped_column(
        Enum(enums.InputCategory, name="input_category"), nullable=False
    )
    product_name: Mapped[ShortText] = mapped_column(nullable=False)
    quantity: Mapped[float | None]
    unit: Mapped[str | None] = mapped_column(String(32))
    cost_paise: Mapped[Paise | None]
    applied_on: Mapped[dt.date | None] = mapped_column(Date)
    source: Mapped[str | None] = mapped_column(String(120))
    attributes: Mapped[Json | None]

    crop_cycle: Mapped[CropCycle] = relationship(back_populates="inputs")


from agrivardhak.domain.models.land import Plot  # noqa: E402
