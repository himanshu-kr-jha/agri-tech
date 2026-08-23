"""Farm Intelligence — M10, FR-511, FR-512, D-15.

What it answers: *given the land, water and capital this collective actually has, which
crop plan raises member income the most per rupee at risk?*

Three things distinguish it from a gross-margin spreadsheet.

**It optimises income per rupee invested, not income (FR-511 / D-06).** A crop that returns
more per acre but needs three times the working capital is not obviously better for a
collective whose binding constraint is cash. Ranking on margin alone quietly recommends
that small farmers borrow.

**Integrated farming is a first-class term, not a footnote (D-15, FR-512).** Manure from
livestock displaces purchased nutrient; crop residue displaces purchased feed. Those flows
are real money and they only appear if you model the farm as a system. A crop-only view
systematically undervalues the mixed smallholding, which is most of this membership.

**It never proposes what the land cannot do.** Water requirement against assured irrigation,
season against the calendar, and area against what is actually operated. A plan that ignores
a rain-fed tract's water ceiling is not optimistic, it is wrong.

What it deliberately does not do: it does not decide. It produces a ranked plan with its
assumptions exposed, and the orchestrator is free to override it on market or risk evidence
— which, on the Prayagraj demo data, is exactly what happens. The Farm module likes potato
on gross margin; the price series says the harvest lands on the annual floor. Both are
correct, and the visible disagreement is the product.

Cost and yield coefficients here are **SYNTHETIC — DEMO ONLY** (seed/sources.md A1-A13,
E1-E6). They are shaped to be plausible for the district and are labelled everywhere they
surface. Replacing one with a cited figure is a one-line change to :data:`CROP_ECONOMICS`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from agrivardhak.domain.units import format_lakh
from agrivardhak.intelligence.contracts import (
    AffectedSet,
    EvidenceRef,
    Finding,
    ModuleInput,
    ModuleOutput,
    ProposedAction,
)

MODULE = "farm_intelligence"
VERSION = "1.0.0"

SYNTHETIC_MARKER = "SYNTHETIC — DEMO ONLY"

#: Coefficients from a labelled placeholder set are never stated above this.
UNSOURCED_CONFIDENCE_CEILING = 0.62

#: Irrigations a crop can be short by and still be grown, with a yield cost.
WATER_GAP_TOLERABLE = 3

#: Yield lost per missing irrigation. ⚠️ SYNTHETIC — DEMO ONLY (seed/sources.md A16).
WATER_SHORTFALL_YIELD_PENALTY = 0.12

SQM_PER_HA = Decimal(10000)
SQM_PER_ACRE = Decimal("4046.86")


@dataclass(frozen=True)
class CropEconomics:
    """Per-hectare economics for one crop option.

    Costs are split by category rather than lumped, because the categories behave
    differently under a constraint: seed and nutrient are cash at sowing, labour is spread,
    and irrigation is only a cost where water is purchased. A single "cost of cultivation"
    number cannot answer "what if we are short of cash in October".
    """

    crop_name: str
    season: str
    seed_paise_per_ha: int
    nutrient_paise_per_ha: int
    protection_paise_per_ha: int
    labour_paise_per_ha: int
    irrigation_paise_per_ha: int
    other_paise_per_ha: int
    #: Irrigations needed over the cycle. The water constraint bites through this.
    irrigations_required: int
    duration_days: int
    #: Nutrient demand, used by the integrated-farming credit.
    nitrogen_kg_per_ha: float
    #: Residue produced, in kg per ha — feed or mulch rather than something to burn.
    residue_kg_per_ha: float
    #: Perennials only: establishment capital spread over the productive life. Excluding it
    #: makes an orchard look like free money, because the money was spent years ago.
    establishment_paise_per_ha_per_year: int = 0
    #: Perennials only: years of cost before the first real harvest.
    years_to_bearing: int = 0
    source: str | None = None

    @property
    def is_perennial(self) -> bool:
        return self.season == "PERENNIAL"

    @property
    def total_cost_paise_per_ha(self) -> int:
        return (
            self.seed_paise_per_ha
            + self.nutrient_paise_per_ha
            + self.protection_paise_per_ha
            + self.labour_paise_per_ha
            + self.irrigation_paise_per_ha
            + self.other_paise_per_ha
            + self.establishment_paise_per_ha_per_year
        )

    def cost_breakdown(self) -> dict[str, int]:
        return {
            "seed": self.seed_paise_per_ha,
            "nutrient": self.nutrient_paise_per_ha,
            "protection": self.protection_paise_per_ha,
            "labour": self.labour_paise_per_ha,
            "irrigation": self.irrigation_paise_per_ha,
            "other": self.other_paise_per_ha,
            **(
                {"establishment_amortised": self.establishment_paise_per_ha_per_year}
                if self.establishment_paise_per_ha_per_year
                else {}
            ),
        }


#: SYNTHETIC — DEMO ONLY. Order-of-magnitude plausible for eastern-UP smallholdings.
CROP_ECONOMICS: dict[str, CropEconomics] = {
    "Potato": CropEconomics(
        crop_name="Potato",
        season="RABI",
        seed_paise_per_ha=4_500_000,
        nutrient_paise_per_ha=1_800_000,
        protection_paise_per_ha=900_000,
        labour_paise_per_ha=2_600_000,
        irrigation_paise_per_ha=700_000,
        other_paise_per_ha=1_000_000,
        irrigations_required=6,
        duration_days=95,
        nitrogen_kg_per_ha=180.0,
        residue_kg_per_ha=2500.0,
    ),
    "Wheat": CropEconomics(
        crop_name="Wheat",
        season="RABI",
        seed_paise_per_ha=700_000,
        nutrient_paise_per_ha=1_400_000,
        protection_paise_per_ha=300_000,
        labour_paise_per_ha=1_200_000,
        irrigation_paise_per_ha=600_000,
        other_paise_per_ha=700_000,
        irrigations_required=5,
        duration_days=140,
        nitrogen_kg_per_ha=150.0,
        residue_kg_per_ha=4000.0,
    ),
    "Mustard": CropEconomics(
        crop_name="Mustard",
        season="RABI",
        seed_paise_per_ha=250_000,
        nutrient_paise_per_ha=900_000,
        protection_paise_per_ha=250_000,
        labour_paise_per_ha=900_000,
        irrigation_paise_per_ha=250_000,
        other_paise_per_ha=500_000,
        irrigations_required=2,
        duration_days=130,
        nitrogen_kg_per_ha=80.0,
        residue_kg_per_ha=2200.0,
    ),
    "Paddy": CropEconomics(
        crop_name="Paddy",
        season="KHARIF",
        seed_paise_per_ha=600_000,
        nutrient_paise_per_ha=1_500_000,
        protection_paise_per_ha=500_000,
        labour_paise_per_ha=2_200_000,
        irrigation_paise_per_ha=1_100_000,
        other_paise_per_ha=800_000,
        irrigations_required=12,
        duration_days=135,
        nitrogen_kg_per_ha=120.0,
        residue_kg_per_ha=5000.0,
    ),
    "Guava": CropEconomics(
        crop_name="Guava",
        season="PERENNIAL",
        seed_paise_per_ha=0,
        nutrient_paise_per_ha=1_200_000,
        protection_paise_per_ha=600_000,
        # Picking, grading and packing 30 t of fruit by hand is the dominant cost of an
        # orchard and dwarfs a cereal's whole labour bill. An earlier figure here was
        # copied from the annual crops and produced a return of 13 rupees per rupee, which
        # is the kind of number that should stop a reviewer rather than excite them.
        labour_paise_per_ha=12_000_000,
        irrigation_paise_per_ha=500_000,
        other_paise_per_ha=3_500_000,
        irrigations_required=8,
        duration_days=365,
        nitrogen_kg_per_ha=100.0,
        residue_kg_per_ha=1200.0,
        # Orchard establishment, amortised. Without it a perennial looks free to plant.
        establishment_paise_per_ha_per_year=2_500_000,
        years_to_bearing=3,
    ),
}

#: Nutrient value of farmyard manure, per kg of nitrogen displaced. SYNTHETIC — DEMO ONLY.
NITROGEN_PAISE_PER_KG = 6_500
#: Feed value of crop residue actually usable as fodder. SYNTHETIC — DEMO ONLY.
RESIDUE_FEED_PAISE_PER_KG = 250
#: Share of residue realistically recoverable as feed rather than lost or ploughed in.
RESIDUE_RECOVERY = 0.45


# --------------------------------------------------------------------------- inputs


@dataclass(frozen=True)
class LandBlock:
    """Area available for planning, grouped by the things that constrain what can grow.

    Grouped rather than per-plot on purpose: a plan expressed as 1,240 individual plot
    instructions is not a plan anyone can approve. Drill-down resolves it back to plots.
    """

    tract: str
    area_sqm: Decimal
    irrigated_share: float
    farmer_ids: list[uuid.UUID]
    plot_ids: list[uuid.UUID] = field(default_factory=list)
    soil_type: str | None = None
    evidence: list[EvidenceRef] = field(default_factory=list)


@dataclass(frozen=True)
class CropOption:
    """A crop the collective could plant, with its expected price and yield."""

    crop_name: str
    season: str
    expected_yield_kg_per_ha: float | None
    #: The price the plan is costed at. A range, because a point price is a false promise.
    price_low_paise_per_kg: int | None
    price_high_paise_per_kg: int | None
    price_evidence: EvidenceRef | None
    #: Yield confidence carried from the Quality module, if it ran.
    yield_confidence: float | None = None
    suitable_tracts: tuple[str, ...] = ()


@dataclass(frozen=True)
class IntegratedAsset:
    """Livestock, compost or agroforestry already on the farms (FR-512, D-15)."""

    kind: str
    count: Decimal
    #: Nitrogen available per unit per year, as manure. SYNTHETIC — DEMO ONLY.
    nitrogen_kg_per_unit_year: float
    #: Fodder demand per unit per year — what residue can offset.
    feed_kg_per_unit_year: float
    farmer_ids: list[uuid.UUID] = field(default_factory=list)
    evidence: list[EvidenceRef] = field(default_factory=list)


@dataclass(frozen=True)
class Constraints:
    """What the plan may not exceed. Unknown is not unlimited."""

    working_capital_paise: int | None
    #: Irrigations the tract's water can actually support over a season, if known.
    irrigations_available: dict[str, int] = field(default_factory=dict)
    max_share_per_crop: float = 0.60
    evidence: list[EvidenceRef] = field(default_factory=list)


# --------------------------------------------------------------------------- outputs


@dataclass(frozen=True)
class CropReturn:
    crop_name: str
    tract: str
    cost_paise_per_ha: int
    revenue_low_paise_per_ha: int
    revenue_high_paise_per_ha: int
    margin_low_paise_per_ha: int
    margin_high_paise_per_ha: int
    #: The ranking metric: margin per rupee of cost. 0.8 means 80 paise back per rupee in.
    return_per_rupee_low: float
    return_per_rupee_high: float
    water_feasible: bool
    notes: list[str]
    confidence: float
    evidence: list[EvidenceRef]
    is_perennial: bool = False

    @property
    def return_per_rupee_mid(self) -> float:
        return (self.return_per_rupee_low + self.return_per_rupee_high) / 2


# --------------------------------------------------------------------------- computation


def crop_return(
    option: CropOption,
    block: LandBlock,
    economics: CropEconomics,
    constraints: Constraints,
) -> CropReturn | None:
    """Cost, revenue band and return per rupee for one crop on one block.

    Returns ``None`` rather than a guess when the yield or the price is unknown. An
    unpriceable option should be absent from the ranking, not present with an invented
    number that will win or lose on that invention.
    """
    if option.expected_yield_kg_per_ha is None:
        return None
    if option.price_low_paise_per_kg is None or option.price_high_paise_per_kg is None:
        return None

    notes: list[str] = []
    cost = economics.total_cost_paise_per_ha

    # Rain-fed land carries the irrigation cost only for what it can actually apply, but
    # gives up yield for it. Charging full irrigation cost on unirrigated land would make
    # the rain-fed tract look expensive as well as unproductive — wrong on both counts.
    if block.irrigated_share < 0.5:
        cost -= int(economics.irrigation_paise_per_ha * (1 - block.irrigated_share))
        notes.append(
            f"{block.irrigated_share:.0%} of this block is irrigated; irrigation cost is "
            "pro-rated and the yield expectation is the rain-fed one."
        )

    # A water shortfall is a yield penalty before it is an impossibility. Farmers on
    # short water grow the crop anyway and get less of it; declaring wheat "not feasible" on
    # the rain-fed tract, where wheat is visibly grown every Rabi, would be the model
    # contradicting the fields. Only a gap wider than WATER_GAP_TOLERABLE excludes.
    available = constraints.irrigations_available.get(block.tract)
    water_feasible = True
    water_penalty = 1.0
    if available is not None and economics.irrigations_required > available:
        shortfall = economics.irrigations_required - available
        if shortfall > WATER_GAP_TOLERABLE:
            water_feasible = False
            notes.append(
                f"Needs {economics.irrigations_required} irrigations against about "
                f"{available} here — a shortfall of {shortfall}. Not viable without a new "
                f"water source."
            )
        else:
            water_penalty = max(0.5, 1.0 - WATER_SHORTFALL_YIELD_PENALTY * shortfall)
            notes.append(
                f"Short by {shortfall} irrigation(s); yield is discounted "
                f"{1 - water_penalty:.0%} rather than the crop being ruled out."
            )

    if option.suitable_tracts and block.tract not in option.suitable_tracts:
        notes.append(f"Not a recorded fit for {block.tract.replace('_', '-').title()} soils.")

    yield_kg = option.expected_yield_kg_per_ha * water_penalty
    revenue_low = int(yield_kg * option.price_low_paise_per_kg)
    revenue_high = int(yield_kg * option.price_high_paise_per_kg)

    confidence = min(
        UNSOURCED_CONFIDENCE_CEILING,
        option.yield_confidence if option.yield_confidence is not None else 0.5,
    )
    evidence = [e for e in (option.price_evidence,) if e is not None] + block.evidence[:2]
    if not evidence:
        return None

    return CropReturn(
        crop_name=option.crop_name,
        tract=block.tract,
        cost_paise_per_ha=cost,
        revenue_low_paise_per_ha=revenue_low,
        revenue_high_paise_per_ha=revenue_high,
        margin_low_paise_per_ha=revenue_low - cost,
        margin_high_paise_per_ha=revenue_high - cost,
        return_per_rupee_low=round((revenue_low - cost) / cost, 3) if cost else 0.0,
        return_per_rupee_high=round((revenue_high - cost) / cost, 3) if cost else 0.0,
        water_feasible=water_feasible,
        notes=notes,
        confidence=confidence,
        evidence=evidence,
        is_perennial=economics.is_perennial,
    )


def integrated_credit(
    assets: list[IntegratedAsset], plan_area_sqm: Decimal, economics: CropEconomics
) -> dict[str, Any]:
    """What the farm system gives back that a crop-only budget misses (FR-512).

    Two flows, both ordinary and both usually unbudgeted: manure nitrogen displacing
    purchased fertiliser, and crop residue displacing purchased fodder. Neither is free
    money — it is money the household is already spending and could stop spending.
    """
    hectares = plan_area_sqm / SQM_PER_HA
    nitrogen_available = sum(
        float(a.count) * a.nitrogen_kg_per_unit_year for a in assets if a.nitrogen_kg_per_unit_year
    )
    nitrogen_needed = float(hectares) * economics.nitrogen_kg_per_ha
    nitrogen_used = min(nitrogen_available, nitrogen_needed)

    feed_demand = sum(float(a.count) * a.feed_kg_per_unit_year for a in assets)
    residue_available = float(hectares) * economics.residue_kg_per_ha * RESIDUE_RECOVERY
    residue_used = min(residue_available, feed_demand)

    return {
        "nitrogen_kg_displaced": round(nitrogen_used, 1),
        "nitrogen_paise_saved": int(nitrogen_used * NITROGEN_PAISE_PER_KG),
        "residue_kg_as_feed": round(residue_used, 1),
        "residue_paise_saved": int(residue_used * RESIDUE_FEED_PAISE_PER_KG),
        "total_paise_saved": int(
            nitrogen_used * NITROGEN_PAISE_PER_KG + residue_used * RESIDUE_FEED_PAISE_PER_KG
        ),
        "nitrogen_demand_kg": round(nitrogen_needed, 1),
        "feed_demand_kg": round(feed_demand, 1),
    }


def capital_feasible(
    returns: list[CropReturn], area_sqm: Decimal, working_capital_paise: int | None
) -> tuple[bool, int, str | None]:
    """Whether the collective can actually fund the plan it is about to be shown.

    A recommendation the FPO cannot pay for is worse than no recommendation: it burns the
    CEO's trust in everything else on the screen.
    """
    if not returns:
        return True, 0, None
    hectares = area_sqm / SQM_PER_HA
    required = int(float(hectares) * returns[0].cost_paise_per_ha)
    if working_capital_paise is None:
        return (
            True,
            required,
            (
                "Working capital is not recorded, so affordability is unchecked — this plan may "
                "not be fundable."
            ),
        )
    if required > working_capital_paise:
        return (
            False,
            required,
            (
                f"Needs Rs {format_lakh(required)} lakh against Rs "
                f"{format_lakh(working_capital_paise)} lakh recorded working capital."
            ),
        )
    return True, required, None


def rank(returns: list[CropReturn]) -> list[CropReturn]:
    """Rank the annual crops on the low end of the return band, not the mid.

    Two rules, both about not being fooled by a number.

    Ranking on the *optimistic* end systematically favours whichever crop has the widest
    price uncertainty, which is precisely backwards for a collective with no buffer.

    **Perennials are excluded entirely**, and that is not a simplification. An established
    orchard's return per rupee of *annual operating cost* is high because the capital was
    spent years ago — on the Prayagraj data guava came out at eleven rupees per rupee, and
    ranking it against wheat would read as "convert the wheat land to guava" while silently
    omitting three years with no income and the establishment cost that buys them. The two
    are different kinds of decision and get reported separately.
    """
    return sorted(
        [r for r in returns if r.water_feasible and not r.is_perennial],
        key=lambda r: (-r.return_per_rupee_low, -r.margin_low_paise_per_ha),
    )


# --------------------------------------------------------------------------- module entry


def run(inputs: ModuleInput) -> ModuleOutput:
    data = inputs.data
    blocks: list[LandBlock] = data.get("blocks") or []
    options: list[CropOption] = data.get("options") or []
    assets: list[IntegratedAsset] = data.get("integrated_assets") or []
    constraints: Constraints = data.get("constraints") or Constraints(working_capital_paise=None)
    season: str | None = data.get("season")
    #: tract -> the crop currently occupying most of it, plus "__dominant__" org-wide. Passed
    #: in by the orchestrator rather than derived, so the module stays a pure function.
    planted: dict[str, str] | None = data.get("planted_crop_by_tract")

    findings: list[Finding] = []
    actions: list[ProposedAction] = []
    degraded: list[str] = [
        f"Cost-of-cultivation coefficients are {SYNTHETIC_MARKER} (seed/sources.md E1-E6); "
        f"confidence is capped at {UNSOURCED_CONFIDENCE_CEILING}."
    ]

    if not blocks:
        return ModuleOutput(
            module=MODULE, version=VERSION, degraded_inputs=[*degraded, "no land blocks"]
        )
    if not options:
        return ModuleOutput(
            module=MODULE, version=VERSION, degraded_inputs=[*degraded, "no crop options priced"]
        )
    if constraints.working_capital_paise is None:
        degraded.append("working capital unknown — plan affordability is unchecked")
    if not assets:
        degraded.append(
            "no livestock or compost recorded — the integrated-farming credit is not applied, "
            "which understates the mixed smallholding"
        )

    for block in blocks:
        returns = [
            r
            for option in options
            if season is None or option.season == season or option.season == "PERENNIAL"
            for economics in [CROP_ECONOMICS.get(option.crop_name)]
            if economics is not None
            for r in [crop_return(option, block, economics, constraints)]
            if r is not None
        ]
        infeasible = [r for r in returns if not r.water_feasible]
        perennials = [r for r in returns if r.is_perennial and r.water_feasible]
        ranked = rank(returns)
        if not ranked:
            degraded.append(f"no feasible crop option for {block.tract}")
            continue

        best = ranked[0]
        runner_up = ranked[1] if len(ranked) > 1 else None
        economics = CROP_ECONOMICS[best.crop_name]
        affordable, required, capital_note = capital_feasible(
            ranked, block.area_sqm, constraints.working_capital_paise
        )

        comparison = ""
        if runner_up is not None:
            comparison = (
                f" Next best is {runner_up.crop_name} at "
                f"{runner_up.return_per_rupee_low:.2f}-{runner_up.return_per_rupee_high:.2f}."
            )
        findings.append(
            Finding(
                key=f"crop_return.{block.tract.lower()}.{best.crop_name.lower()}",
                statement=(
                    f"{block.tract.replace('_', '-').title()}: {best.crop_name} returns "
                    f"{best.return_per_rupee_low:.2f} to {best.return_per_rupee_high:.2f} "
                    f"rupees per rupee of cost on "
                    f"{float(block.area_sqm / SQM_PER_ACRE):,.0f} acres.{comparison} "
                    f"[{SYNTHETIC_MARKER} costs]"
                ),
                magnitude=Decimal(str(best.return_per_rupee_low)),
                unit="return per rupee (low end)",
                confidence=best.confidence,
                evidence=best.evidence,
                assumptions=[
                    f"Cost of cultivation is {SYNTHETIC_MARKER}, not a surveyed figure.",
                    "Ranked on the low end of the price band, so a crop is not preferred "
                    "merely for having a wider spread of possible outcomes.",
                    *best.notes,
                    *([capital_note] if capital_note else []),
                ],
                affected=AffectedSet(
                    farmer_ids=block.farmer_ids,
                    plot_ids=block.plot_ids,
                    area_sqm=block.area_sqm,
                    value_paise=int(
                        float(block.area_sqm / SQM_PER_HA) * best.margin_low_paise_per_ha
                    ),
                ),
            )
        )

        for orchard in perennials:
            economics_p = CROP_ECONOMICS[orchard.crop_name]
            findings.append(
                Finding(
                    key=f"perennial_return.{block.tract.lower()}.{orchard.crop_name.lower()}",
                    statement=(
                        f"{block.tract.replace('_', '-').title()}: {orchard.crop_name} on "
                        f"established orchard returns "
                        f"{orchard.return_per_rupee_low:.2f} to "
                        f"{orchard.return_per_rupee_high:.2f} per rupee of annual operating "
                        f"cost — high because the establishment capital was spent "
                        f"{economics_p.years_to_bearing} years ago. Not comparable with the "
                        f"annual crops and not ranked against them. [{SYNTHETIC_MARKER} costs]"
                    ),
                    magnitude=Decimal(str(orchard.return_per_rupee_low)),
                    unit="return per rupee of annual cost",
                    confidence=orchard.confidence,
                    evidence=orchard.evidence,
                    assumptions=[
                        "Applies to orchards already bearing. Planting new orchard means "
                        f"about {economics_p.years_to_bearing} years of cost before income.",
                        "Establishment capital is amortised into the cost, but the years of "
                        "foregone income from the land are not priced here.",
                        f"Costs are {SYNTHETIC_MARKER}.",
                    ],
                    affected=AffectedSet(farmer_ids=block.farmer_ids, area_sqm=block.area_sqm),
                )
            )

        # Where the crop the collective is *already growing* sits in this ranking.
        #
        # The module computes a return for every option and then reports only the winner,
        # which throws away the more actionable half: an FPO with 99% of its area in one crop
        # does not need to be told which crop scores highest in the abstract, it needs to know
        # where its own crop sits and by how much. Naming the incumbent is also what lets the
        # orchestrator see a genuine cross-module disagreement about it — without this the
        # Farm module's findings are all about crops nobody is growing, so they can never
        # meet the override quorum however strongly they point.
        incumbent_name = (planted or {}).get(block.tract) or (planted or {}).get("__dominant__")
        if incumbent_name and len(ranked) > 1:
            position = next(
                (i for i, r in enumerate(ranked) if r.crop_name == incumbent_name), None
            )
            if position is not None and position > 0:
                incumbent = ranked[position]
                leader = ranked[0]
                findings.append(
                    Finding(
                        key=f"underperforming_crop.{incumbent_name.lower()}",
                        statement=(
                            f"{block.tract.replace('_', '-').title()}: {incumbent_name} — the "
                            f"crop actually planted here — ranks {position + 1} of "
                            f"{len(ranked)} on return per rupee "
                            f"({incumbent.return_per_rupee_low:.2f} against "
                            f"{leader.crop_name}'s {leader.return_per_rupee_low:.2f}). "
                            f"[{SYNTHETIC_MARKER} costs]"
                        ),
                        magnitude=Decimal(
                            str(
                                round(
                                    leader.return_per_rupee_low - incumbent.return_per_rupee_low,
                                    3,
                                )
                            )
                        ),
                        unit="return per rupee foregone",
                        confidence=incumbent.confidence,
                        evidence=incumbent.evidence,
                        assumptions=[
                            f"Cost of cultivation is {SYNTHETIC_MARKER}; the ordering is more "
                            "trustworthy than the magnitudes.",
                            "Return per rupee is not the only reason to grow a crop. Paddy "
                            "and wheat carry assured procurement, household food security and "
                            "a labour calendar the alternatives do not — none of which this "
                            "module prices.",
                        ],
                        affected=AffectedSet(
                            farmer_ids=block.farmer_ids,
                            plot_ids=block.plot_ids,
                            area_sqm=block.area_sqm,
                        ),
                    )
                )

        if infeasible:
            names = ", ".join(sorted({r.crop_name for r in infeasible}))
            findings.append(
                Finding(
                    key=f"water_constraint.{block.tract.lower()}",
                    statement=(
                        f"{block.tract.replace('_', '-').title()}: {names} excluded — the "
                        f"tract's water cannot support the irrigations required."
                    ),
                    confidence=0.70,
                    evidence=infeasible[0].evidence,
                    assumptions=[
                        "Irrigation availability is a tract-level estimate, not a measured "
                        "water budget per plot.",
                    ],
                    affected=AffectedSet(farmer_ids=block.farmer_ids, area_sqm=block.area_sqm),
                )
            )

        if assets:
            credit = integrated_credit(assets, block.area_sqm, economics)
            if credit["total_paise_saved"] > 0:
                asset_evidence = [e for a in assets for e in a.evidence][:2] or best.evidence
                findings.append(
                    Finding(
                        key=f"integrated_credit.{block.tract.lower()}",
                        statement=(
                            f"Livestock manure covers {credit['nitrogen_kg_displaced']:,.0f} kg "
                            f"of the {credit['nitrogen_demand_kg']:,.0f} kg nitrogen this plan "
                            f"needs, and residue covers "
                            f"{credit['residue_kg_as_feed']:,.0f} kg of fodder — about Rs "
                            f"{format_lakh(credit['total_paise_saved'])} lakh of purchases "
                            f"the plan would otherwise make. [{SYNTHETIC_MARKER} rates]"
                        ),
                        magnitude=Decimal(credit["total_paise_saved"]),
                        unit="paise",
                        confidence=0.55,
                        evidence=asset_evidence,
                        assumptions=[
                            "Manure nitrogen and fodder values are placeholders, not assays.",
                            f"Only {RESIDUE_RECOVERY:.0%} of residue is treated as "
                            "recoverable as feed; the rest is lost, bedded or ploughed in.",
                            "This is spending avoided, not income earned.",
                        ],
                        affected=AffectedSet(
                            farmer_ids=block.farmer_ids,
                            area_sqm=block.area_sqm,
                            value_paise=credit["total_paise_saved"],
                        ),
                    )
                )

        afford_note = (
            "Affordable within recorded working capital." if affordable else (capital_note or "")
        )
        actions.append(
            ProposedAction(
                key=f"crop_plan.{block.tract.lower()}",
                title=(
                    f"{block.tract.replace('_', '-').title()}: lead with {best.crop_name} on "
                    f"{float(block.area_sqm / SQM_PER_ACRE):,.0f} acres"
                ),
                rationale=(
                    f"Highest return per rupee of the options this tract's water and season "
                    f"allow, ranked on the pessimistic end of the price band. "
                    f"{afford_note}"
                ),
                recommendation_type="CROP_PLAN",
                target_type="tract",
                target_id=None,
                value_paise=int(float(block.area_sqm / SQM_PER_HA) * best.margin_low_paise_per_ha),
                value_unit="paise_margin_low",
                expected_impact={
                    "metric": "member income per rupee invested",
                    "range": [best.return_per_rupee_low, best.return_per_rupee_high],
                    "capital_required_paise": required,
                    "affordable": affordable,
                    "cost_breakdown_per_ha": economics.cost_breakdown(),
                    "data_status": SYNTHETIC_MARKER,
                },
                risks=[
                    "Costed at historical prices; the realised price is what decides this.",
                    "A single dominant crop concentrates the collective's whole season.",
                    *([capital_note] if capital_note else []),
                ],
                alternatives=[
                    f"{r.crop_name}: {r.return_per_rupee_low:.2f}-{r.return_per_rupee_high:.2f} "
                    f"per rupee"
                    for r in ranked[1:4]
                ],
                confidence=best.confidence,
                evidence=best.evidence,
            )
        )

    return ModuleOutput(
        module=MODULE,
        version=VERSION,
        findings=findings,
        proposed_actions=actions,
        degraded_inputs=degraded,
    )
