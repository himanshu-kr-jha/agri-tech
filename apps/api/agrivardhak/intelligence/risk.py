"""Risk Intelligence — M8, FR-551…555.

What this module is for
-----------------------
An FPO does not need to be told that farming is risky. It needs to know **which of its own
acres are exposed, to what, how likely, and what it would cost to do something about it**.
So every finding here carries an :class:`AffectedSet`: farmers, area, tonnage, rupees. A
hazard with no exposure attached is a weather report, not a decision input (FR-554).

Where the numbers come from
---------------------------
Two real sources, and one deliberate refusal.

**Weather hazard** is a frequency, not a forecast: 30 years of ERA5 reanalysis at the tract
point, bucketed into half-months, asking *in what fraction of those years did this window
see a heavy-rain day?* That is a checkable statement about the record. It is emphatically
not a prediction that it will rain this February, and the wording of every finding keeps
that distinction visible — ``prediction != recommendation`` (INV-6) has a sibling here,
*climatology != forecast*.

**Price risk** comes from 24 months of Agmarknet modal prices for the actual markets this
FPO sells into. The finding that matters on Prayagraj data is seasonal: potato's harvest
window sits on the annual price trough, which is a fact about the series, not a model.

**The refusal**: this module does not compute a probability for anything it has no record
of. Pest outbreak likelihood, policy change, buyer default — all real risks, none of them
derivable from what we hold. They are reported as ``degraded_inputs``, which lowers the
confidence of anything built on top, rather than being filled in with a plausible number.
A fabricated 0.7 is indistinguishable from a measured 0.7 once it is on a screen.

A note on an earlier mistake, kept because it is instructive: the architecture sketch for
this module used an illustrative "unseasonal rain probability 0.71" for the February potato
window. The real figure from the record is **0.167**. Building the demo on the invented
number would have produced a more dramatic story and a false one, and the correction is
what moved the potato case from a weather story to a price story — which is what the data
actually supports.
"""

from __future__ import annotations

import datetime as dt
import statistics
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from agrivardhak.intelligence.contracts import (
    AffectedSet,
    EvidenceRef,
    Finding,
    ModuleInput,
    ModuleOutput,
    ProposedAction,
)

MODULE = "risk_intelligence"
VERSION = "1.0.0"

#: Below this share of a year's price range, a window counts as a trough worth flagging.
#: 0.35 rather than 0.5: a window merely below the midpoint is unremarkable, and flagging it
#: would bury the genuine troughs in noise.
TROUGH_PERCENTILE = 0.35

#: A crop holding more than this share of organization area is a concentration exposure.
#: One third is the point where a single crop failure stops being absorbable.
CONCENTRATION_SHARE = 0.33

#: A buyer holding more than this share of offered volume is a counterparty exposure.
BUYER_CONCENTRATION_SHARE = 0.50

#: Hazard probabilities below this are not worth a CEO's attention as a standalone finding.
#: They still enter the register, and they still qualify any recommendation that ignores them.
HAZARD_REPORTABLE = 0.15

#: Above this, a hazard has stopped being a hazard and become the climate.
#:
#: This threshold exists because of a finding the demo data produced: heat-stress days above
#: 40 C occurred in the late-April window in **100% of the last 30 years**. That is not a
#: risk — it is April in Prayagraj, the crop calendar already accounts for it, and no farmer
#: needs telling. Ranked naively it beat a 1,868-tonne price exposure to the top of the
#: packet, because a probability of 1.0 scores maximally on every axis that treats
#: probability as severity.
#:
#: A near-certain event carries no decision information. It is reported as a standing
#: condition with low urgency rather than as something to act on.
HAZARD_IS_CLIMATE_ABOVE = 0.90

LIKELIHOOD_BANDS = ((0.66, "HIGH"), (0.33, "MEDIUM"), (0.0, "LOW"))

HAZARD_LABEL = {
    "heavy_rain": "a heavy-rain day (>=15 mm)",
    "very_heavy_rain": "a very-heavy-rain day (>=40 mm)",
    "frost": "a frost day (min <=4 C)",
    "heat_stress": "a heat-stress day (max >=40 C)",
}

#: Which hazards actually threaten which crop, and in which phase. Judgement, stated openly
#: rather than hidden in a coefficient: rain on a standing or lifted crop is a harvest
#: hazard; terminal heat is a grain-fill hazard and so applies before harvest, not at it.
HARVEST_HAZARDS = ("heavy_rain", "very_heavy_rain")
GRAIN_FILL_HAZARDS = ("heat_stress",)


# --------------------------------------------------------------------------- inputs


@dataclass(frozen=True)
class HazardWindow:
    """One half-month bucket of the climatological record."""

    key: str
    years_observed: int
    probability: dict[str, float]
    mean_rain_mm_per_day: float | None = None


@dataclass(frozen=True)
class Climatology:
    """Hazard frequencies for one tract, derived from the long record.

    ``years_observed`` is carried into confidence deliberately. Thirty years of record and
    three years of record produce the same-looking fraction and deserve very different
    trust, and the only place that difference can be honoured is here.
    """

    tract: str
    windows: dict[str, HazardWindow]
    evidence: EvidenceRef

    def window_for(self, date: dt.date) -> HazardWindow | None:
        return self.windows.get(f"{date.month:02d}{'A' if date.day <= 15 else 'B'}")

    def over_span(self, start: dt.date, end: dt.date) -> dict[str, float]:
        """Probability that *at least one* hazard day falls anywhere in a multi-week span.

        Combined as ``1 - prod(1 - p)`` across the windows the span touches. The windows are
        not independent — a stalled western disturbance spans both halves of a month — so
        this reads high rather than exact. A harvest that straddles three windows genuinely
        carries more exposure than one that fits inside a fortnight, and treating them as
        equal would erase the whole reason to stagger a harvest.
        """
        touched = self._windows_between(start, end)
        if not touched:
            return {}
        combined: dict[str, float] = {}
        for hazard in HAZARD_LABEL:
            survival = 1.0
            for window in touched:
                survival *= 1.0 - window.probability.get(hazard, 0.0)
            combined[hazard] = round(1.0 - survival, 3)
        return combined

    def years_over_span(self, start: dt.date, end: dt.date) -> int:
        touched = self._windows_between(start, end)
        return min((w.years_observed for w in touched), default=0)

    def _windows_between(self, start: dt.date, end: dt.date) -> list[HazardWindow]:
        keys: list[str] = []
        cursor = start
        while cursor <= end and len(keys) < 26:
            key = f"{cursor.month:02d}{'A' if cursor.day <= 15 else 'B'}"
            if key not in keys:
                keys.append(key)
            cursor += dt.timedelta(days=14)
        end_key = f"{end.month:02d}{'A' if end.day <= 15 else 'B'}"
        if end_key not in keys:
            keys.append(end_key)
        return [self.windows[k] for k in keys if k in self.windows]


@dataclass(frozen=True)
class MonthlyPrice:
    month: int
    median_paise_per_kg: int
    median_arrivals_kg: Decimal | None
    samples: int


@dataclass(frozen=True)
class PriceSeasonality:
    """A crop's price and arrival shape across the year, from the real series.

    Twenty-four months is two observations per calendar month — thin, and the confidence
    reflects it. It is still the difference between "potato is cheap in February" as folk
    knowledge and as something the FPO can point at.
    """

    crop_name: str
    months: dict[int, MonthlyPrice]
    evidence: EvidenceRef

    @property
    def low(self) -> MonthlyPrice | None:
        return min(self.months.values(), key=lambda m: m.median_paise_per_kg, default=None)

    @property
    def high(self) -> MonthlyPrice | None:
        return max(self.months.values(), key=lambda m: m.median_paise_per_kg, default=None)

    def position(self, month: int) -> float | None:
        """Where a month sits in the year's price range: 0.0 = annual low, 1.0 = annual high."""
        point = self.months.get(month)
        low, high = self.low, self.high
        if point is None or low is None or high is None:
            return None
        span = high.median_paise_per_kg - low.median_paise_per_kg
        if span <= 0:
            return None
        return (point.median_paise_per_kg - low.median_paise_per_kg) / span

    def arrival_ratio(self, month: int) -> float | None:
        """Arrivals in a month against the year's median month. >1 means a glut."""
        point = self.months.get(month)
        volumes = [
            float(m.median_arrivals_kg)
            for m in self.months.values()
            if m.median_arrivals_kg is not None
        ]
        if point is None or point.median_arrivals_kg is None or len(volumes) < 6:
            return None
        baseline = statistics.median(volumes)
        return float(point.median_arrivals_kg) / baseline if baseline > 0 else None

    @property
    def min_samples(self) -> int:
        return min((m.samples for m in self.months.values()), default=0)


@dataclass(frozen=True)
class CropExposure:
    """What the organization actually has standing in one crop.

    Every field is what a mitigation would be sized against, which is why the module
    computes nothing it cannot attach to a farmer id.
    """

    crop_name: str
    farmer_ids: list[uuid.UUID]
    crop_cycle_ids: list[uuid.UUID]
    area_sqm: Decimal
    expected_kg: Decimal | None
    harvest_from: dt.date | None
    harvest_to: dt.date | None
    tract: str | None = None
    #: Tract → area, for a hazard that differs by tract even when the rainfall does not.
    area_by_tract: dict[str, Decimal] = field(default_factory=dict)
    evidence: list[EvidenceRef] = field(default_factory=list)


@dataclass(frozen=True)
class BuyerExposure:
    buyer_id: uuid.UUID
    buyer_name: str
    offered_kg: Decimal
    crop_name: str
    reliability: float | None
    evidence: EvidenceRef


@dataclass(frozen=True)
class RiskEntry:
    """The register row a finding resolves to (FR-552). Persisted by the orchestrator."""

    key: str
    domain: str
    title: str
    likelihood: str
    impact: str
    probability: float | None
    horizon_start: dt.date | None
    horizon_end: dt.date | None
    affected: AffectedSet
    mitigation: str | None
    confidence: float
    evidence: list[EvidenceRef]


# --------------------------------------------------------------------------- computation


def likelihood_band(probability: float) -> str:
    for threshold, label in LIKELIHOOD_BANDS:
        if probability >= threshold:
            return label
    return "LOW"


def impact_band(value_paise: int | None, working_capital_paise: int | None) -> str:
    """Impact is relative to what the organization can absorb, not an absolute rupee figure.

    Six lakh is survivable for one collective and existential for another. Without a known
    working capital the honest answer is MEDIUM — refusing to rank rather than inventing a
    denominator.
    """
    if value_paise is None or working_capital_paise is None or working_capital_paise <= 0:
        return "MEDIUM"
    share = value_paise / working_capital_paise
    if share >= 0.25:
        return "HIGH"
    if share >= 0.08:
        return "MEDIUM"
    return "LOW"


def climatology_confidence(years_observed: int) -> float:
    """Trust in a frequency, as a function of how many years produced it.

    Thirty years earns 0.80 — high, but never certainty, because the record is reanalysis at
    a coarse grid point rather than a gauge in the field, and because a stationary-climate
    assumption is doing quiet work underneath any climatology.
    """
    if years_observed >= 30:
        return 0.80
    if years_observed >= 20:
        return 0.72
    if years_observed >= 10:
        return 0.62
    if years_observed >= 5:
        return 0.50
    return 0.35


def seasonality_confidence(min_samples: int, months_covered: int) -> float:
    if months_covered < 8:
        return 0.35
    if min_samples >= 40:
        return 0.78
    if min_samples >= 20:
        return 0.70
    if min_samples >= 8:
        return 0.60
    return 0.45


def _acres(area_sqm: Decimal) -> float:
    return float(area_sqm) / 4046.86


def _harvest_month(exposure: CropExposure) -> int | None:
    if exposure.harvest_from is None:
        return None
    return exposure.harvest_from.month


# --------------------------------------------------------------------------- findings


def price_trough_risk(
    exposure: CropExposure,
    seasonality: PriceSeasonality,
    working_capital_paise: int | None,
) -> tuple[Finding, RiskEntry] | None:
    """The finding the Prayagraj data actually supports.

    Potato lifts in February at a median 1,000 paise/kg against a November median of 1,950 —
    the harvest sits on the annual floor. That is not a forecast and not a model; it is the
    shape of the series the FPO already sells into, and it is the largest single lever on
    member income in the whole dataset.
    """
    month = _harvest_month(exposure)
    if month is None:
        return None
    position = seasonality.position(month)
    point = seasonality.months.get(month)
    peak = seasonality.high
    if position is None or point is None or peak is None or position > TROUGH_PERCENTILE:
        return None
    if exposure.expected_kg is None or exposure.expected_kg <= 0:
        return None

    gap_paise_per_kg = peak.median_paise_per_kg - point.median_paise_per_kg
    foregone_paise = int(gap_paise_per_kg * float(exposure.expected_kg))
    confidence = seasonality_confidence(seasonality.min_samples, len(seasonality.months))

    statement = (
        f"{exposure.crop_name} harvests into its annual price trough: the "
        f"{dt.date(2000, month, 1):%B} median at the markets this FPO sells into is "
        f"Rs {point.median_paise_per_kg / 100:.2f}/kg against Rs "
        f"{peak.median_paise_per_kg / 100:.2f}/kg in "
        f"{dt.date(2000, peak.month, 1):%B} — a gap of Rs {gap_paise_per_kg / 100:.2f}/kg "
        f"across {float(exposure.expected_kg) / 1000:,.0f} t."
    )
    affected = AffectedSet(
        farmer_ids=exposure.farmer_ids,
        crop_cycle_ids=exposure.crop_cycle_ids,
        area_sqm=exposure.area_sqm,
        quantity_kg=exposure.expected_kg,
        value_paise=foregone_paise,
    )
    evidence = [seasonality.evidence, *exposure.evidence[:3]]
    finding = Finding(
        key=f"price_trough.{exposure.crop_name.lower()}",
        statement=statement,
        magnitude=Decimal(foregone_paise),
        unit="paise",
        confidence=confidence,
        evidence=evidence,
        assumptions=[
            "Seasonal shape is taken from 24 months of Agmarknet modal prices — two "
            "observations per calendar month, which is thin. It shows a shape, not a level.",
            "The peak-month price is not a price this FPO is guaranteed; it is the median "
            "the market cleared at, before storage cost, shrinkage and the capital tied up.",
        ],
        affected=affected,
    )
    entry = RiskEntry(
        key=finding.key,
        domain="MARKET",
        title=f"{exposure.crop_name} harvest coincides with the annual price floor",
        likelihood="HIGH",
        impact=impact_band(foregone_paise, working_capital_paise),
        probability=None,
        horizon_start=exposure.harvest_from,
        horizon_end=exposure.harvest_to,
        affected=affected,
        mitigation="Stagger sale across the post-harvest months, or store into the recovery.",
        confidence=confidence,
        evidence=evidence,
    )
    return finding, entry


def arrival_glut_risk(
    exposure: CropExposure, seasonality: PriceSeasonality
) -> tuple[Finding, RiskEntry] | None:
    """Why the trough exists: everyone harvests at once.

    Separated from the price finding on purpose. The price gap says *what it costs*; the
    arrival ratio says *why*, and the why is what tells a CEO the trough is structural and
    will still be there next year rather than a bad fortnight to wait out.
    """
    month = _harvest_month(exposure)
    if month is None:
        return None
    ratio = seasonality.arrival_ratio(month)
    if ratio is None or ratio < 1.5:
        return None
    point = seasonality.months[month]
    confidence = min(seasonality_confidence(seasonality.min_samples, len(seasonality.months)), 0.70)
    affected = AffectedSet(
        farmer_ids=exposure.farmer_ids,
        crop_cycle_ids=exposure.crop_cycle_ids,
        area_sqm=exposure.area_sqm,
        quantity_kg=exposure.expected_kg,
    )
    statement = (
        f"{exposure.crop_name} arrivals in {dt.date(2000, month, 1):%B} run "
        f"{ratio:.1f}x the year's median month at these markets — the trough is a glut, "
        f"so it recurs rather than passing."
    )
    evidence = [seasonality.evidence, *exposure.evidence[:2]]
    finding = Finding(
        key=f"arrival_glut.{exposure.crop_name.lower()}",
        statement=statement,
        magnitude=Decimal(str(round(ratio, 2))),
        unit="x median month",
        confidence=confidence,
        evidence=evidence,
        assumptions=[
            "Arrivals are reported per market and are known to be incomplete on holidays; "
            f"this month rests on {point.samples} reported days.",
        ],
        affected=affected,
    )
    entry = RiskEntry(
        key=finding.key,
        domain="MARKET",
        title=f"{exposure.crop_name} harvest-window glut at the local mandis",
        likelihood="HIGH",
        impact="MEDIUM",
        probability=None,
        horizon_start=exposure.harvest_from,
        horizon_end=exposure.harvest_to,
        affected=affected,
        mitigation="Aggregate and sell outside the peak-arrival fortnight.",
        confidence=confidence,
        evidence=evidence,
    )
    return finding, entry


def weather_hazard_risk(
    exposure: CropExposure,
    climatology: Climatology,
    working_capital_paise: int | None,
    price_paise_per_kg: int | None,
) -> list[tuple[Finding, RiskEntry]]:
    """Climatological exposure over the harvest window. A frequency, said as a frequency."""
    if exposure.harvest_from is None or exposure.harvest_to is None:
        return []
    probabilities = climatology.over_span(exposure.harvest_from, exposure.harvest_to)
    years = climatology.years_over_span(exposure.harvest_from, exposure.harvest_to)
    if not probabilities or years == 0:
        return []

    confidence = climatology_confidence(years)
    out: list[tuple[Finding, RiskEntry]] = []
    for hazard in (*HARVEST_HAZARDS, *GRAIN_FILL_HAZARDS):
        probability = probabilities.get(hazard, 0.0)
        if probability < HAZARD_REPORTABLE:
            continue
        is_climate = probability >= HAZARD_IS_CLIMATE_ABOVE
        value_paise = (
            int(price_paise_per_kg * float(exposure.expected_kg) * probability * 0.15)
            if price_paise_per_kg and exposure.expected_kg
            else None
        )
        affected = AffectedSet(
            farmer_ids=exposure.farmer_ids,
            crop_cycle_ids=exposure.crop_cycle_ids,
            area_sqm=exposure.area_sqm,
            quantity_kg=exposure.expected_kg,
            value_paise=value_paise,
        )
        window = f"{exposure.harvest_from:%d %b} to {exposure.harvest_to:%d %b}"
        place = climatology.tract.replace("_", "-").title()
        if is_climate:
            statement = (
                f"{exposure.crop_name}: {HAZARD_LABEL[hazard]} fell in the {window} harvest "
                f"window in {probability:.0%} of the last {years} years at the {place} point. "
                f"At that frequency this is the normal climate rather than a risk — noted so "
                f"the crop calendar can be checked against it, not as something to act on."
            )
        else:
            statement = (
                f"{exposure.crop_name}: in {probability:.0%} of the last {years} years, "
                f"{HAZARD_LABEL[hazard]} fell somewhere in the {window} harvest window at "
                f"the {place} point — {_acres(exposure.area_sqm):,.0f} acres are in that "
                f"window."
            )
        evidence = [climatology.evidence, *exposure.evidence[:2]]
        finding = Finding(
            key=(
                f"climate_normal.{hazard}.{exposure.crop_name.lower()}"
                if is_climate
                else f"weather_hazard.{hazard}.{exposure.crop_name.lower()}"
            ),
            statement=statement,
            magnitude=Decimal(str(probability)),
            unit="probability",
            confidence=confidence,
            evidence=evidence,
            assumptions=[
                "This is the historical frequency in the record, not a forecast for this "
                "season. It says how often the window has been hit, not that it will be.",
                *(
                    [
                        "At this frequency the event is effectively certain, so it carries "
                        "no information for a decision — it is a planning constant."
                    ]
                    if is_climate
                    else []
                ),
                "ERA5 reanalysis at a ~25 km grid point, not a gauge in these fields.",
                "Loss is sized at 15% of exposed value if the hazard lands — a placeholder "
                "damage ratio, not a measured one (seed/sources.md A14).",
            ],
            affected=affected,
        )
        entry = RiskEntry(
            key=finding.key,
            domain="WEATHER",
            title=f"{HAZARD_LABEL[hazard].capitalize()} in the {exposure.crop_name} harvest window",
            likelihood=likelihood_band(probability),
            impact="LOW" if is_climate else impact_band(value_paise, working_capital_paise),
            probability=probability,
            horizon_start=exposure.harvest_from,
            horizon_end=exposure.harvest_to,
            affected=affected,
            mitigation=(
                "Stagger the lift so the whole crop is not exposed on the same days; "
                "confirm covered storage before the window opens."
            ),
            confidence=confidence,
            evidence=evidence,
        )
        out.append((finding, entry))
    return out


def concentration_risk(
    exposures: list[CropExposure], working_capital_paise: int | None
) -> list[tuple[Finding, RiskEntry]]:
    """One crop carrying too much of the collective.

    Deliberately *not* framed as "grow less potato". Concentration is a fact about the
    portfolio; whether to accept it is a decision that belongs to the board, and a module
    that turned an exposure into an instruction would be overstepping (INV-1).
    """
    total = sum((e.area_sqm for e in exposures), Decimal(0))
    if total <= 0:
        return []
    out: list[tuple[Finding, RiskEntry]] = []
    for exposure in exposures:
        share = float(exposure.area_sqm / total)
        if share < CONCENTRATION_SHARE:
            continue
        affected = AffectedSet(
            farmer_ids=exposure.farmer_ids,
            crop_cycle_ids=exposure.crop_cycle_ids,
            area_sqm=exposure.area_sqm,
            quantity_kg=exposure.expected_kg,
        )
        evidence = exposure.evidence[:3]
        if not evidence:
            continue
        confidence = 0.90  # a count of our own acres; the uncertainty is in the plot areas
        finding = Finding(
            key=f"concentration.{exposure.crop_name.lower()}",
            statement=(
                f"{exposure.crop_name} is {share:.0%} of operated area "
                f"({_acres(exposure.area_sqm):,.0f} of {_acres(total):,.0f} acres) across "
                f"{len(exposure.farmer_ids)} farmers — one crop's season moves the "
                f"collective's whole result."
            ),
            magnitude=Decimal(str(round(share, 3))),
            unit="share of area",
            confidence=confidence,
            evidence=evidence,
            assumptions=[
                "Plot areas carry their own provenance and some are farmer-reported; the "
                "share is as good as those measurements.",
            ],
            affected=affected,
        )
        entry = RiskEntry(
            key=finding.key,
            domain="MARKET",
            title=f"Portfolio concentration in {exposure.crop_name}",
            likelihood="HIGH",
            impact=impact_band(None, working_capital_paise),
            probability=None,
            horizon_start=exposure.harvest_from,
            horizon_end=exposure.harvest_to,
            affected=affected,
            mitigation=(
                "A board decision, not a module's: the concentration may be the right bet. "
                "It is recorded so it is chosen rather than drifted into."
            ),
            confidence=confidence,
            evidence=evidence,
        )
        out.append((finding, entry))
    return out


def buyer_concentration_risk(buyers: list[BuyerExposure]) -> tuple[Finding, RiskEntry] | None:
    """Counterparty exposure: one buyer holding most of a crop's offered volume."""
    if not buyers:
        return None
    by_buyer: dict[uuid.UUID, tuple[str, Decimal, float | None, EvidenceRef]] = {}
    for buyer in buyers:
        name, volume, reliability, evidence = by_buyer.get(
            buyer.buyer_id, (buyer.buyer_name, Decimal(0), buyer.reliability, buyer.evidence)
        )
        by_buyer[buyer.buyer_id] = (name, volume + buyer.offered_kg, reliability, evidence)
    total = sum((v[1] for v in by_buyer.values()), Decimal(0))
    if total <= 0:
        return None
    buyer_id, (name, volume, reliability, evidence) = max(by_buyer.items(), key=lambda kv: kv[1][1])
    share = float(volume / total)
    if share < BUYER_CONCENTRATION_SHARE:
        return None

    reliability_note = (
        f" Their recorded reliability is {reliability:.0%}."
        if reliability is not None
        else " No reliability history is recorded for them, which is itself the exposure."
    )
    affected = AffectedSet(buyer_ids=[buyer_id], quantity_kg=volume)
    confidence = 0.75 if reliability is not None else 0.55
    finding = Finding(
        key="buyer_concentration",
        statement=(
            f"{name} accounts for {share:.0%} of all offered volume "
            f"({float(volume) / 1000:,.0f} t).{reliability_note}"
        ),
        magnitude=Decimal(str(round(share, 3))),
        unit="share of offered volume",
        confidence=confidence,
        evidence=[evidence],
        assumptions=["Offered volume, not contracted volume — an offer can be withdrawn."],
        affected=affected,
    )
    entry = RiskEntry(
        key=finding.key,
        domain="SUPPLY_CHAIN",
        title=f"Counterparty concentration: {name}",
        likelihood="MEDIUM",
        impact="HIGH",
        probability=None,
        horizon_start=None,
        horizon_end=None,
        affected=affected,
        mitigation="Split the lot across at least two buyers, or take part-payment on lifting.",
        confidence=confidence,
        evidence=[evidence],
    )
    return finding, entry


# --------------------------------------------------------------------------- module entry


def run(inputs: ModuleInput) -> ModuleOutput:
    """Assemble the register. Pure — every input arrives in ``inputs.data`` (ARCHITECTURE §3)."""
    data = inputs.data
    exposures: list[CropExposure] = data.get("exposures") or []
    climatology: dict[str, Climatology] = data.get("climatology") or {}
    seasonality: dict[str, PriceSeasonality] = data.get("seasonality") or {}
    buyers: list[BuyerExposure] = data.get("buyer_exposures") or []
    working_capital: int | None = data.get("working_capital_paise")
    current_price: dict[str, int] = data.get("current_price_paise_per_kg") or {}

    findings: list[Finding] = []
    actions: list[ProposedAction] = []
    entries: list[RiskEntry] = []
    degraded: list[str] = []

    if not exposures:
        return ModuleOutput(
            module=MODULE, version=VERSION, degraded_inputs=["no crop cycles to assess"]
        )
    if not climatology:
        degraded.append("no hazard climatology — weather exposure not assessed")
    if not seasonality:
        degraded.append("no price series — seasonal exposure not assessed")
    if working_capital is None:
        degraded.append("working capital unknown — impact bands are unranked")

    # Risks we know exist and cannot size. Named rather than silently omitted (NFR-301).
    degraded.append(
        "pest and disease outbreak likelihood is not modelled — no surveillance history"
    )
    degraded.append("policy and procurement change is not modelled — no scheme feed yet")

    for exposure in exposures:
        season = seasonality.get(exposure.crop_name)
        if season is not None:
            trough = price_trough_risk(exposure, season, working_capital)
            if trough:
                findings.append(trough[0])
                entries.append(trough[1])
                actions.append(_stagger_action(exposure, trough[1], season))
            glut = arrival_glut_risk(exposure, season)
            if glut:
                findings.append(glut[0])
                entries.append(glut[1])
        elif exposure.expected_kg:
            degraded.append(f"no price series for {exposure.crop_name}")

        tract_climate = climatology.get(exposure.tract or "") or next(
            iter(climatology.values()), None
        )
        if tract_climate is not None:
            for finding, entry in weather_hazard_risk(
                exposure, tract_climate, working_capital, current_price.get(exposure.crop_name)
            ):
                findings.append(finding)
                entries.append(entry)
                if (
                    entry.domain == "WEATHER"
                    and entry.likelihood in ("MEDIUM", "HIGH")
                    and not finding.key.startswith("climate_normal.")
                ):
                    actions.append(_hazard_action(exposure, entry))

    for finding, entry in concentration_risk(exposures, working_capital):
        findings.append(finding)
        entries.append(entry)

    counterparty = buyer_concentration_risk(buyers)
    if counterparty:
        findings.append(counterparty[0])
        entries.append(counterparty[1])
        actions.append(_split_lot_action(counterparty[1]))

    return ModuleOutput(
        module=MODULE,
        version=VERSION,
        findings=findings,
        proposed_actions=actions,
        degraded_inputs=degraded,
    )


def register_entries(output: ModuleOutput, inputs: ModuleInput) -> list[RiskEntry]:
    """Re-derive the register rows for persistence.

    The register is a side effect of the same computation, and recomputing it here rather
    than smuggling ORM rows through ``ModuleOutput`` is what keeps the module pure and
    replayable. Cheap: the work is arithmetic over already-gathered inputs.
    """
    data = inputs.data
    exposures: list[CropExposure] = data.get("exposures") or []
    climatology: dict[str, Climatology] = data.get("climatology") or {}
    seasonality: dict[str, PriceSeasonality] = data.get("seasonality") or {}
    buyers: list[BuyerExposure] = data.get("buyer_exposures") or []
    working_capital: int | None = data.get("working_capital_paise")
    current_price: dict[str, int] = data.get("current_price_paise_per_kg") or {}

    entries: list[RiskEntry] = []
    for exposure in exposures:
        season = seasonality.get(exposure.crop_name)
        if season is not None:
            trough = price_trough_risk(exposure, season, working_capital)
            if trough:
                entries.append(trough[1])
            glut = arrival_glut_risk(exposure, season)
            if glut:
                entries.append(glut[1])
        tract_climate = climatology.get(exposure.tract or "") or next(
            iter(climatology.values()), None
        )
        if tract_climate is not None:
            entries.extend(
                entry
                for _, entry in weather_hazard_risk(
                    exposure, tract_climate, working_capital, current_price.get(exposure.crop_name)
                )
            )
    entries.extend(entry for _, entry in concentration_risk(exposures, working_capital))
    counterparty = buyer_concentration_risk(buyers)
    if counterparty:
        entries.append(counterparty[1])
    return entries


def _stagger_action(
    exposure: CropExposure, entry: RiskEntry, seasonality: PriceSeasonality
) -> ProposedAction:
    peak = seasonality.high
    recovery = f" toward {dt.date(2000, peak.month, 1):%B}" if peak else ""
    return ProposedAction(
        key=f"stagger_sale.{exposure.crop_name.lower()}",
        title=f"Stagger the {exposure.crop_name} sale out of the harvest trough",
        rationale=(
            f"The whole crop currently lands in the cheapest fortnight of the year. Moving "
            f"part of it{recovery} converts a calendar accident into member income. The "
            f"trade-off is real and belongs in the decision: storage cost, weight loss in "
            f"store, and the working capital that stays tied up until the sale."
        ),
        recommendation_type="RISK_MITIGATION",
        target_type="crop",
        target_id=None,
        value_paise=entry.affected.value_paise,
        value_unit="paise_foregone",
        expected_impact={
            "metric": "realised price per kg",
            "direction": "increase",
            "basis": "difference between harvest-month and peak-month medians",
            "not_guaranteed": (
                "The peak-month median is what the market cleared at in past years, "
                "before storage cost and shrinkage. It is not a price on offer."
            ),
        },
        risks=[
            "Storage cost and weight loss can exceed the seasonal gain in a flat year.",
            "Holding ties up working capital that members may need at harvest.",
            "If every FPO stores, the recovery month is itself flattened.",
        ],
        alternatives=[
            "Sell at harvest and accept the trough price — the current default.",
            "Sell part at harvest for member cash flow and store the balance.",
        ],
        confidence=entry.confidence,
        evidence=entry.evidence,
    )


def _hazard_action(exposure: CropExposure, entry: RiskEntry) -> ProposedAction:
    return ProposedAction(
        key=f"stagger_harvest.{exposure.crop_name.lower()}.{entry.domain.lower()}",
        title=f"Spread the {exposure.crop_name} harvest across the exposed window",
        rationale=(
            f"{entry.probability:.0%} of the last years saw this hazard somewhere in the "
            f"window. Lifting the whole crop on the same three days concentrates that "
            f"exposure; spreading it does not reduce the chance of rain, it reduces how much "
            f"is standing when it comes."
            if entry.probability is not None
            else "Spreading the lift reduces how much is exposed on any one day."
        ),
        recommendation_type="RISK_MITIGATION",
        target_type="crop",
        target_id=None,
        value_paise=entry.affected.value_paise,
        value_unit="paise_at_risk",
        expected_impact={
            "metric": "quantity exposed on a single day",
            "direction": "decrease",
            "note": "Reduces exposure; does not change the hazard probability.",
        },
        risks=[
            "A staggered lift needs more labour-days and more transport trips.",
            "Part of the crop stays in the ground longer and keeps its field risk.",
        ],
        alternatives=["Lift on schedule and carry the exposure."],
        confidence=entry.confidence,
        evidence=entry.evidence,
    )


def _split_lot_action(entry: RiskEntry) -> ProposedAction:
    return ProposedAction(
        key="split_counterparty",
        title=entry.title,
        rationale=(
            "A single buyer holding most of the volume sets the price and carries all the "
            "default risk. Splitting costs a little in price and buys a second option."
        ),
        recommendation_type="RISK_MITIGATION",
        target_type="buyer",
        target_id=entry.affected.buyer_ids[0] if entry.affected.buyer_ids else None,
        value_paise=None,
        value_unit=None,
        expected_impact={"metric": "counterparty concentration", "direction": "decrease"},
        risks=["Two smaller consignments may each fetch less than one large one."],
        alternatives=["Keep the single buyer and negotiate part-payment on lifting."],
        confidence=entry.confidence,
        evidence=entry.evidence,
    )


def summarise(entries: list[RiskEntry]) -> dict[str, Any]:
    """Counts for the dashboard card and the risk-register screen."""
    by_domain: dict[str, int] = {}
    by_likelihood: dict[str, int] = {}
    for entry in entries:
        by_domain[entry.domain] = by_domain.get(entry.domain, 0) + 1
        by_likelihood[entry.likelihood] = by_likelihood.get(entry.likelihood, 0) + 1
    exposed_farmers = {f for e in entries for f in e.affected.farmer_ids}
    at_risk_value = sum(e.affected.value_paise or 0 for e in entries)
    return {
        "total": len(entries),
        "by_domain": by_domain,
        "by_likelihood": by_likelihood,
        "farmers_exposed": len(exposed_farmers),
        "value_at_risk_paise": at_risk_value,
    }
