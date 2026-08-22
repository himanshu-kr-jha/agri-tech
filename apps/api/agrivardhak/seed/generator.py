"""Generate the synthetic Prayagraj FPO.

Deterministic (DR-09): a fixed RNG seed means two runs produce identical content, so the
demo is reproducible and `make seed` twice is a no-op in effect.

Everything generated here is synthetic and flagged as such. What is *not* synthetic is the
structure it is drawn from — real block names, real Agmarknet market ids, the real GI guava
blocks — so the shape of the data is defensible even though the individuals are invented.
"""

from __future__ import annotations

import datetime as dt
import random
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agrivardhak.domain import enums
from agrivardhak.domain.models.crops import Crop, CropCycle, Variety
from agrivardhak.domain.models.land import Farm, Plot, PlotTenure
from agrivardhak.domain.models.market import Buyer
from agrivardhak.domain.models.organization import (
    Farmer,
    Membership,
    Organization,
    OrgResource,
    RoleGrant,
    User,
)
from agrivardhak.domain.models.provenance import AttributePolicy, DataSource
from agrivardhak.domain.units import hectares_to_sqm
from agrivardhak.provenance import resolver, trust
from agrivardhak.seed import reference as ref

SEED = 20260822
TODAY = dt.date(2026, 8, 22)
NOW = dt.datetime(2026, 8, 22, 6, 0, tzinfo=dt.UTC)

#: Plots seeded with tenure shares that deliberately do not sum to 100%, so the discrepancy
#: path has real data behind the demo's provenance moment (docs/DEMO-CONTEXT.md §5.3).
CONFLICTED_TENURE_PLOTS = 12

#: Plots given three conflicting area claims (farmer / record / field officer).
CONFLICTED_AREA_PLOTS = 8

FIRST_NAMES = [
    "Ravi",
    "Suresh",
    "Anil",
    "Rajesh",
    "Ram",
    "Shyam",
    "Mohan",
    "Dinesh",
    "Vinod",
    "Ashok",
    "Sunita",
    "Kamla",
    "Geeta",
    "Rekha",
    "Savitri",
    "Meena",
    "Pushpa",
    "Sarita",
    "Urmila",
    "Ramesh",
    "Mukesh",
    "Santosh",
    "Arun",
    "Vijay",
    "Rakesh",
    "Prem",
    "Hari",
    "Gopal",
]
SURNAMES = [
    "Yadav",
    "Patel",
    "Singh",
    "Verma",
    "Mishra",
    "Tiwari",
    "Pandey",
    "Kushwaha",
    "Maurya",
    "Nishad",
    "Bind",
    "Pal",
    "Sharma",
    "Gupta",
    "Kumar",
    "Dubey",
    "Shukla",
    "Sahu",
]


@dataclass
class SeedResult:
    organization_id: uuid.UUID
    farmers: int
    plots: int
    crop_cycles: int
    observations: int
    discrepancies: int
    total_area_sqm: float


# --------------------------------------------------------------------------- helpers


def _name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAMES)}"


def _holding_ha(rng: random.Random, mean_ha: float) -> float:
    """Log-normal around the class mean, clipped so a 'marginal' farmer stays marginal."""
    value = rng.lognormvariate(0, 0.35) * mean_ha
    return max(0.15, min(value, mean_ha * 2.4))


def _season_for(today: dt.date) -> tuple[enums.Season, int]:
    """Which season is currently active. Kharif Jun-Oct, Rabi Nov-Mar, Zaid Apr-May."""
    if 6 <= today.month <= 10:
        return enums.Season.KHARIF, today.year
    if today.month >= 11:
        return enums.Season.RABI, today.year
    if today.month <= 3:
        return enums.Season.RABI, today.year - 1
    return enums.Season.ZAID, today.year


# --------------------------------------------------------------------------- seeding


def seed_all(session: Session, *, rng_seed: int = SEED) -> SeedResult:
    """Idempotent: if the organization already exists, nothing is re-created."""
    existing = (
        session.execute(select(Organization).where(Organization.name == ref.ORG_NAME))
        .scalars()
        .first()
    )
    if existing is not None:
        return _summarize(session, existing)

    rng = random.Random(rng_seed)

    _seed_attribute_policies(session)
    sources = _seed_data_sources(session)
    org = _seed_organization(session)
    crops = _seed_crops(session)
    _seed_buyers(session, org, rng)
    _seed_users(session, org)

    farmers = _seed_farmers(session, org, rng)
    plots = _seed_land(session, farmers, rng)
    cycles = _seed_crop_cycles(session, plots, crops, rng)
    obs, disc = _seed_observations(session, plots, cycles, sources, rng)

    session.flush()
    return SeedResult(
        organization_id=org.id,
        farmers=len(farmers),
        plots=len(plots),
        crop_cycles=len(cycles),
        observations=obs,
        discrepancies=disc,
        total_area_sqm=sum(float(p.area_sqm) for p in plots),
    )


def _summarize(session: Session, org: Organization) -> SeedResult:
    from agrivardhak.domain.models.provenance import DataDiscrepancy, Observation

    farmers = session.execute(
        select(func.count()).select_from(Membership).where(Membership.organization_id == org.id)
    ).scalar_one()
    plots = session.execute(select(func.count()).select_from(Plot)).scalar_one()
    cycles = session.execute(select(func.count()).select_from(CropCycle)).scalar_one()
    obs = session.execute(select(func.count()).select_from(Observation)).scalar_one()
    disc = session.execute(select(func.count()).select_from(DataDiscrepancy)).scalar_one()
    area = session.execute(select(func.coalesce(func.sum(Plot.area_sqm), 0))).scalar_one()
    return SeedResult(org.id, farmers, plots, cycles, obs, disc, float(area))


def _seed_attribute_policies(session: Session) -> None:
    for policy in trust.DEFAULT_POLICIES.values():
        session.add(
            AttributePolicy(
                attribute=policy.attribute,
                half_life_days=policy.half_life_days,
                stale_after_days=policy.stale_after_days,
                tolerance_pct=policy.tolerance_pct,
            )
        )
    session.flush()


def _seed_data_sources(session: Session) -> dict[str, DataSource]:
    out: dict[str, DataSource] = {}
    for spec in ref.DATA_SOURCES:
        source = DataSource(
            key=spec.key,
            label=spec.label,
            source_type=spec.source_type,
            base_trust=spec.base_trust,
            url=spec.url,
            is_fixture=spec.is_fixture,
        )
        session.add(source)
        out[spec.key] = source
    session.flush()
    return out


def _seed_organization(session: Session) -> Organization:
    org = Organization(
        type=enums.OrganizationType.FPO,
        name=ref.ORG_NAME,
        legal_form="Producer Company",
        district=ref.ORG_DISTRICT,
        state=ref.ORG_STATE,
        is_synthetic=True,
    )
    session.add(org)
    session.flush()

    for rtype, label, qty, unit, value_paise in ref.ORG_RESOURCES:
        session.add(
            OrgResource(
                organization_id=org.id,
                type=rtype,
                label=label,
                quantity=qty,
                unit=unit,
                value_paise=value_paise,
            )
        )
    session.flush()
    return org


def _seed_crops(session: Session) -> dict[str, list[Variety]]:
    out: dict[str, list[Variety]] = {}
    for spec in ref.CROPS:
        crop = Crop(
            name=spec.name,
            name_hi=spec.name_hi,
            default_season=spec.season,
            is_perennial=spec.is_perennial,
        )
        session.add(crop)
        session.flush()
        varieties = []
        for vspec in spec.varieties:
            variety = Variety(
                crop_id=crop.id,
                name=vspec.name,
                duration_days=vspec.duration_days,
                base_yield_kg_per_ha=vspec.base_yield_kg_per_ha,
                water_requirement_mm=vspec.water_requirement_mm,
                agro_zone="Central Plain Zone",
                source_ref=vspec.source_ref,
                # Synthetic unless the coefficient itself is cited (seed/sources.md A1-A5).
                is_synthetic=vspec.source_ref is None,
            )
            session.add(variety)
            varieties.append(variety)
        session.flush()
        out[spec.name] = varieties
    return out


def _seed_buyers(session: Session, org: Organization, rng: random.Random) -> None:
    """The eight demo buyers (docs/DEMO-CONTEXT.md §6.2).

    B1 vs B2 is the effective-price reversal: B2 offers more per kg but lands less in a
    farmer's hand once 180 km of freight, 60-day terms and rejection risk are netted out.
    """
    specs = [
        ("Ganga Cold Store Aggregator", enums.BuyerType.AGGREGATOR, 22, 15, 0.92, 0.03),
        ("Kanpur Wholesale Traders", enums.BuyerType.WHOLESALER, 180, 60, 0.68, 0.11),
        ("Northern Foods Processing", enums.BuyerType.PROCESSOR, 95, 30, 0.85, 0.07),
        ("Handia Rice Mill", enums.BuyerType.PROCESSOR, 18, 7, 0.95, 0.02),
        ("Govt Procurement Centre", enums.BuyerType.GOVERNMENT, 12, 21, 0.90, 0.01),
        ("Meja Oil Mill", enums.BuyerType.PROCESSOR, 40, 20, 0.80, 0.05),
        ("Sangam Premium Fruit Traders", enums.BuyerType.RETAILER, 30, 10, 0.88, 0.06),
        ("Metro E-Commerce Sourcing", enums.BuyerType.ECOMMERCE, 140, 45, 0.74, 0.14),
    ]
    for name, btype, distance, terms, reliability, rejection in specs:
        session.add(
            Buyer(
                organization_id=org.id,
                name=name,
                type=btype,
                location=ref.ORG_DISTRICT,
                distance_km=distance,
                payment_terms_days=terms,
                reliability=reliability,
                rejection_rate=rejection,
                min_quantity_kg=rng.choice([5_000, 10_000, 25_000, 50_000]),
                max_quantity_kg=rng.choice([200_000, 300_000, 500_000]),
                is_synthetic=True,
            )
        )
    session.flush()


def _seed_users(session: Session, org: Organization) -> None:
    ceo = User(display_name="FPO CEO (demo)", email="ceo@demo.agrivardhak", locale="en-IN")
    admin = User(
        display_name="Platform Admin (demo)", email="admin@demo.agrivardhak", locale="en-IN"
    )
    session.add_all([ceo, admin])
    session.flush()
    session.add_all(
        [
            RoleGrant(user_id=ceo.id, organization_id=org.id, role=enums.Role.FPO_CEO),
            RoleGrant(user_id=admin.id, organization_id=None, role=enums.Role.PLATFORM_ADMIN),
        ]
    )
    session.flush()


def _seed_farmers(session: Session, org: Organization, rng: random.Random) -> list[Farmer]:
    """1,000 farmers distributed across the three tracts by TractProfile.farmer_share."""
    block_by_tract: dict[str, list[tuple[str, str]]] = {
        "GANGA_PAR": [],
        "DOAB": [],
        "YAMUNA_PAR": [],
    }
    for tehsil, blocks in ref.TEHSIL_BLOCKS.items():
        tract = ref.TEHSIL_TRACT[tehsil]
        for block in blocks:
            block_by_tract[tract].append((tehsil, block))

    farmers: list[Farmer] = []
    plan: list[str] = []
    for tract, profile in ref.TRACTS.items():
        plan.extend([tract] * round(profile.farmer_share * 1000))
    while len(plan) < 1000:
        plan.append("GANGA_PAR")
    plan = plan[:1000]
    rng.shuffle(plan)

    for tract in plan:
        tehsil, block = rng.choice(block_by_tract[tract])
        farmer = Farmer(
            full_name=_name(rng),
            phone=f"9{rng.randint(100000000, 999999999)}",
            locale="hi-IN",
            village=f"{block} village {rng.randint(1, 40)}",
            block=block,
            district=ref.ORG_DISTRICT,
            state=ref.ORG_STATE,
            tract=tract,
            household_size=rng.randint(3, 9),
            # Sensitive attributes: consent-gated, used ONLY for scheme eligibility (FR-566).
            category=rng.choices(["GEN", "OBC", "SC", "ST"], weights=[20, 50, 27, 3])[0],
            is_woman_farmer=rng.random() < 0.18,
            is_synthetic=True,
        )
        session.add(farmer)
        farmers.append(farmer)
    session.flush()

    for farmer in farmers:
        session.add(
            Membership(
                farmer_id=farmer.id,
                organization_id=org.id,
                role=enums.MembershipRole.MEMBER,
                status=enums.MembershipStatus.ACTIVE,
                joined_at=TODAY - dt.timedelta(days=rng.randint(200, 1800)),
                shares_held=rng.choice([10, 20, 50, 100]),
                is_primary=True,
            )
        )
    session.flush()
    return farmers


def _seed_land(session: Session, farmers: list[Farmer], rng: random.Random) -> list[Plot]:
    """Farms, plots and tenure — normalised so total area hits the documented target."""
    classes: list[float] = []
    for _label, count, mean_ha in ref.HOLDING_CLASSES:
        classes.extend(_holding_ha(rng, mean_ha) for _ in range(count))
    rng.shuffle(classes)
    # Normalise to the documented 976.2 ha so the demo's headline acreage is reproducible.
    scale = ref.TARGET_TOTAL_HA / sum(classes)
    classes = [ha * scale for ha in classes]

    plots: list[Plot] = []
    for farmer, holding_ha in zip(farmers, classes, strict=False):
        farm = Farm(
            operator_farmer_id=farmer.id,
            label=f"{farmer.full_name.split()[0]}'s farm",
            village=farmer.village,
        )
        session.add(farm)
        session.flush()

        n_plots = 1 if holding_ha < 0.6 else (2 if holding_ha < 1.8 else 3)
        shares = [rng.uniform(0.6, 1.4) for _ in range(n_plots)]
        total = sum(shares)
        profile = ref.TRACTS[farmer.tract or "DOAB"]

        for index, share in enumerate(shares, start=1):
            area_sqm = float(hectares_to_sqm(Decimal(str(holding_ha * share / total))))
            plot = Plot(
                farm_id=farm.id,
                label=f"Plot {index}",
                area_sqm=round(area_sqm, 2),
                soil_type=profile.soil_type,
                irrigation_source=(
                    rng.choice(["Tubewell", "Canal", "Borewell"])
                    if rng.random() < profile.irrigation_coverage
                    else "Rain-fed"
                ),
            )
            session.add(plot)
            plots.append(plot)
    session.flush()

    _seed_tenure(session, farmers, plots, rng)
    return plots


def _seed_tenure(
    session: Session, farmers: list[Farmer], plots: list[Plot], rng: random.Random
) -> None:
    """Tenure mix, including deliberate share conflicts (ADR-0003).

    Twelve plots get shares that do not sum to 100%. Those are not bugs — real land records
    are messy, and the system must surface the gap rather than refuse the write.
    """
    farm_operator = {
        farm.id: farm.operator_farmer_id for farm in session.execute(select(Farm)).scalars()
    }
    conflicted = set(rng.sample(range(len(plots)), CONFLICTED_TENURE_PLOTS))

    for index, plot in enumerate(plots):
        holder_id = farm_operator[plot.farm_id]
        tenure_type = rng.choices(
            [
                enums.TenureType.OWNED,
                enums.TenureType.LEASED,
                enums.TenureType.SHARECROPPED,
                enums.TenureType.JOINT,
            ],
            weights=[72, 14, 9, 5],
        )[0]

        if tenure_type is enums.TenureType.JOINT:
            other = rng.choice(farmers).id
            first = rng.choice([50, 60, 40])
            second = 100 - first if index not in conflicted else first  # conflict: sums to >100
            for holder, share in ((holder_id, first), (other, second)):
                session.add(
                    PlotTenure(
                        plot_id=plot.id,
                        holder_farmer_id=holder,
                        tenure_type=tenure_type,
                        share_pct=share,
                        valid_from=TODAY - dt.timedelta(days=rng.randint(400, 2000)),
                    )
                )
        else:
            share = 100 if index not in conflicted else rng.choice([70, 85, 90])
            session.add(
                PlotTenure(
                    plot_id=plot.id,
                    holder_farmer_id=holder_id,
                    tenure_type=tenure_type,
                    share_pct=share,
                    valid_from=TODAY - dt.timedelta(days=rng.randint(400, 2000)),
                )
            )
    session.flush()


def _seed_crop_cycles(
    session: Session,
    plots: list[Plot],
    crops: dict[str, list[Variety]],
    rng: random.Random,
) -> list[CropCycle]:
    """Two closed seasons plus the active one, so the learning loop has real history."""
    season, year = _season_for(TODAY)

    # Resolve plot -> (tract, block) in two queries rather than per-plot lookups. Which
    # tract a plot is in decides which crops are plausible on it, so this drives the whole
    # geographic pattern the Risk module's clustering later depends on.
    farmers_by_id = {f.id: f for f in session.execute(select(Farmer)).scalars()}
    operator_by_farm = {
        farm.id: farm.operator_farmer_id for farm in session.execute(select(Farm)).scalars()
    }

    plot_context: dict[uuid.UUID, tuple[str, str | None]] = {}
    for plot in plots:
        operator_id = operator_by_farm.get(plot.farm_id)
        operator = farmers_by_id.get(operator_id) if operator_id else None
        plot_context[plot.id] = (
            (operator.tract or "DOAB") if operator else "DOAB",
            operator.block if operator else None,
        )

    crop_by_name = {spec.name: spec for spec in ref.CROPS}
    cycles: list[CropCycle] = []

    windows = [
        (enums.Season.KHARIF, 2024, enums.CropCycleStatus.CLOSED),
        (enums.Season.RABI, 2024, enums.CropCycleStatus.CLOSED),
        (enums.Season.KHARIF, 2025, enums.CropCycleStatus.CLOSED),
        (enums.Season.RABI, 2025, enums.CropCycleStatus.CLOSED),
        (season, year, enums.CropCycleStatus.GROWING),
    ]

    for plot in plots:
        tract, block = plot_context[plot.id]

        for cycle_season, cycle_year, status in windows:
            candidates = [
                spec
                for spec in crop_by_name.values()
                if tract in spec.tracts
                and (spec.season is cycle_season or spec.is_perennial)
                and (spec.name != "Guava" or block in ref.GI_GUAVA_BLOCKS)
            ]
            if not candidates:
                continue
            # Guava is a perennial premium sliver, not a major crop by acreage (§4.2).
            spec = rng.choices(
                candidates,
                weights=[3 if s.name == "Guava" else 30 for s in candidates],
            )[0]
            variety = rng.choice(crops[spec.name])

            sowing = _sowing_date(cycle_season, cycle_year, rng)
            duration = variety.duration_days or 300
            cycles.append(
                CropCycle(
                    plot_id=plot.id,
                    variety_id=variety.id,
                    season=cycle_season,
                    season_year=cycle_year,
                    status=status,
                    area_sqm=plot.area_sqm,
                    sowing_date=sowing,
                    expected_harvest_date=sowing + dt.timedelta(days=duration),
                    actual_harvest_date=(
                        sowing + dt.timedelta(days=duration + rng.randint(-6, 10))
                        if status is enums.CropCycleStatus.CLOSED
                        else None
                    ),
                    farming_method=rng.choice(["Conventional", "Conventional", "IPM"]),
                )
            )
    session.add_all(cycles)
    session.flush()
    return cycles


def _sowing_date(season: enums.Season, year: int, rng: random.Random) -> dt.date:
    if season is enums.Season.KHARIF:
        return dt.date(year, 6, 20) + dt.timedelta(days=rng.randint(0, 25))
    if season is enums.Season.RABI:
        return dt.date(year, 11, 5) + dt.timedelta(days=rng.randint(0, 25))
    if season is enums.Season.ZAID:
        return dt.date(year, 3, 15) + dt.timedelta(days=rng.randint(0, 15))
    return dt.date(year, 7, 1)


def _seed_observations(
    session: Session,
    plots: list[Plot],
    cycles: list[CropCycle],
    sources: dict[str, DataSource],
    rng: random.Random,
) -> tuple[int, int]:
    """Observations with mixed provenance, including deliberate three-way area conflicts.

    The conflicts are the point: without them the demo's provenance moment has nothing to
    show, and the discrepancy machinery is untested against real data.
    """
    count = 0
    # Track ids, not increments: one conflict is touched by each of its claims,
    # and counting hits would report three where there is one.
    discrepancy_ids: set[uuid.UUID] = set()

    conflicted = set(rng.sample(range(len(plots)), CONFLICTED_AREA_PLOTS))
    for index, plot in enumerate(plots):
        truth = float(plot.area_sqm)
        if index in conflicted:
            # Farmer over-reports, the old record under-reports, the officer is in between —
            # the pattern from the discovery session.
            claims = [
                (truth * 1.11, enums.SourceType.FARMER_SELF_REPORT, "farmer-app", 40),
                (truth * 0.89, enums.SourceType.EXTERNAL_SOURCE, "org-register", 700),
                (truth, enums.SourceType.FIELD_OFFICER, "field-officer", 7),
            ]
        else:
            claims = [(truth, enums.SourceType.FIELD_OFFICER, "field-officer", rng.randint(5, 300))]

        for value, source_type, source_key, days_ago in claims:
            _, discrepancy = resolver.record_observation(
                session,
                subject_type="plot",
                subject_id=plot.id,
                attribute="area_sqm",
                value_numeric=Decimal(str(round(value, 2))),
                unit="sqm",
                source_type=source_type,
                source=sources[source_key],
                observed_at=NOW - dt.timedelta(days=days_ago),
                recorded_at=NOW - dt.timedelta(days=days_ago),
            )
            count += 1
            if discrepancy is not None:
                discrepancy_ids.add(discrepancy.id)

    # Crop health on the active cycles only — a health reading on a closed cycle is history,
    # not a current fact, and would decay to irrelevance anyway.
    active = [c for c in cycles if c.status is enums.CropCycleStatus.GROWING]
    for cycle in active:
        source_key, source_type = rng.choices(
            [
                ("field-officer", enums.SourceType.FIELD_OFFICER),
                ("farmer-app", enums.SourceType.FARMER_SELF_REPORT),
                ("vision-model", enums.SourceType.AI_INFERENCE),
            ],
            weights=[55, 30, 15],
        )[0]
        resolver.record_observation(
            session,
            subject_type="crop_cycle",
            subject_id=cycle.id,
            attribute="crop_health_pct",
            value_numeric=Decimal(str(rng.randint(48, 96))),
            unit="pct",
            source_type=source_type,
            source=sources[source_key],
            observed_at=NOW - dt.timedelta(days=rng.randint(0, 25)),
            recorded_at=NOW - dt.timedelta(days=rng.randint(0, 25)),
            reported_confidence=rng.uniform(0.55, 0.9)
            if source_type is enums.SourceType.AI_INFERENCE
            else None,
        )
        count += 1

    session.flush()
    return count, len(discrepancy_ids)
