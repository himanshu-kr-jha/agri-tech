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
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from agrivardhak.domain import enums
from agrivardhak.domain.models.crops import Crop, CropCycle, Variety
from agrivardhak.domain.models.land import Farm, FarmResource, Plot, PlotTenure
from agrivardhak.domain.models.market import Buyer, DemandSignal, Lot, LotItem
from agrivardhak.domain.models.organization import (
    Announcement,
    Farmer,
    Membership,
    Organization,
    OrgResource,
    RoleGrant,
    User,
)
from agrivardhak.domain.models.provenance import AttributePolicy, DataSource
from agrivardhak.domain.units import hectares_to_sqm
from agrivardhak.ingestion.agmarknet import latest_modal_paise_per_kg, load_series
from agrivardhak.ingestion.policy import load_policy_events
from agrivardhak.ingestion.registry import load_all
from agrivardhak.ingestion.weather import load_weather
from agrivardhak.knowledge.extract import apply_fixture
from agrivardhak.knowledge.pipeline import backfill_embeddings, observe
from agrivardhak.orchestrator import gather
from agrivardhak.provenance import resolver, trust
from agrivardhak.seed import reference as ref
from agrivardhak.seed.learning import seed_learning_loop

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
    price_records: int = 0
    weather_records: int = 0
    lots: int = 0
    offers: int = 0
    decisions: int = 0
    pending: int = 0
    interventions: int = 0
    attributions: int = 0
    predictions_scored: int = 0
    external_records: int = 0
    knowledge_chunks: int = 0
    policy_events: int = 0


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
    _seed_announcements(session, org)

    farmers = _seed_farmers(session, org, rng)
    plots = _seed_land(session, farmers, rng)
    cycles = _seed_crop_cycles(session, plots, crops, rng)
    obs, disc = _seed_observations(session, plots, cycles, sources, rng)

    # Real prices first: the buyer offers below are anchored to them, so an FPO is never
    # shown negotiating at four times what the crop actually trades at.
    price_records = load_series(session)
    weather_records = load_weather(session)
    weather_records += gather.load_climatology_files(session)

    # The ten fetched public sources (seed/generated/batch*/), then the observer that turns
    # the text-bearing ones into retrievable, gated passages. Both are idempotent, and both
    # read committed payloads, so this path stays offline (NFR-303).
    external_records = sum(load_all(session).values())
    observed = observe(session)
    backfill_embeddings(session)
    # Committed extraction proposals, if anyone has run `make extract-schemes` and reviewed
    # the diff. They land UNVERIFIED and capped; attaching them cannot promote anything.
    apply_fixture(session)
    policy_events = load_policy_events(session)
    _seed_farm_resources(session, rng)
    lots = _seed_lots(session, org, cycles, rng)
    offers = _seed_offers(session, org, lots, rng)
    _seed_farmer_login(session, org, farmers)

    # Two prior seasons of closed decision loops, so the Impact panel has something honest
    # to report. Everything before this line describes a collective that has not yet decided
    # anything; this is what makes the learning loop visible. See seed/learning.py.
    loop = seed_learning_loop(session, org, rng)

    session.flush()
    return SeedResult(
        organization_id=org.id,
        farmers=len(farmers),
        plots=len(plots),
        crop_cycles=len(cycles),
        observations=obs,
        discrepancies=disc,
        total_area_sqm=sum(float(p.area_sqm) for p in plots),
        price_records=price_records,
        weather_records=weather_records,
        lots=len(lots),
        offers=offers,
        decisions=loop.packets,
        pending=loop.pending,
        interventions=loop.interventions,
        attributions=loop.attributions,
        predictions_scored=loop.predictions_scored,
        external_records=external_records,
        knowledge_chunks=observed.chunks_written,
        policy_events=policy_events,
    )


def _summarize(session: Session, org: Organization) -> SeedResult:
    """Count what is actually in the database, for the already-seeded path.

    Every field is counted, including prices, weather, lots and offers. An earlier version
    left those at their zero defaults, so running ``make seed`` a second time printed
    "price records 0 / weather days 0 / lots 0" — and anyone following the README would
    reasonably conclude the seed had broken. It had not; the summary was lying by omission.
    """
    from agrivardhak.domain.models.decisions import (
        Attribution,
        DecisionPacket,
        Intervention,
        Prediction,
        Recommendation,
    )
    from agrivardhak.domain.models.knowledge import KnowledgeChunk
    from agrivardhak.domain.models.market import NewsEvent
    from agrivardhak.domain.models.provenance import (
        DataDiscrepancy,
        ExternalRecord,
        Observation,
    )

    def count(model: type[Any], *where: ColumnElement[bool]) -> int:
        stmt = select(func.count()).select_from(model)
        for clause in where:
            stmt = stmt.where(clause)
        return int(session.execute(stmt).scalar_one())

    area = session.execute(select(func.coalesce(func.sum(Plot.area_sqm), 0))).scalar_one()
    return SeedResult(
        organization_id=org.id,
        farmers=count(Membership, Membership.organization_id == org.id),
        plots=count(Plot),
        crop_cycles=count(CropCycle),
        observations=count(Observation),
        discrepancies=count(DataDiscrepancy),
        total_area_sqm=float(area),
        price_records=count(
            ExternalRecord, ExternalRecord.kind == enums.ExternalRecordKind.MARKET_PRICE
        ),
        weather_records=count(
            ExternalRecord, ExternalRecord.kind == enums.ExternalRecordKind.WEATHER
        ),
        lots=count(Lot, Lot.organization_id == org.id),
        offers=count(DemandSignal, DemandSignal.organization_id == org.id),
        decisions=count(DecisionPacket, DecisionPacket.organization_id == org.id),
        pending=count(
            Recommendation,
            Recommendation.organization_id == org.id,
            Recommendation.status == enums.RecommendationStatus.SUGGESTED,
        ),
        interventions=count(Intervention),
        attributions=count(Attribution),
        predictions_scored=count(Prediction, Prediction.actual_value.is_not(None)),
        external_records=count(ExternalRecord),
        knowledge_chunks=count(KnowledgeChunk),
        policy_events=count(NewsEvent, NewsEvent.is_synthetic.is_(False)),
    )


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
    """Staff accounts. The farmer account is created later, once farmers exist.

    All of these can sign in with :data:`agrivardhak.api.login.DEMO_PASSWORD` and are flagged
    ``is_demo_account`` so the sign-in page can offer them and so nothing mistakes them for
    real credentials.

    Hashed at the production iteration count, not a reduced one. An earlier version used
    50,000 rounds to keep seeding fast, which cost about 0.8 s in total — and made a real
    password check four times cheaper than the dummy check the login endpoint runs for an
    unknown username, reopening the timing oracle from the other side. Under a second is not
    worth a hole.
    """
    ceo = User(
        display_name="Ramesh Verma — CEO",
        email="ceo@demo.agrivardhak",
        locale="en-IN",
        password_hash=_demo_hash(),
        is_demo_account=True,
    )
    officer = User(
        display_name="Sunita Devi — Field Officer",
        email="officer@demo.agrivardhak",
        locale="en-IN",
        password_hash=_demo_hash(),
        is_demo_account=True,
    )
    admin = User(
        display_name="Platform Admin (demo)",
        email="admin@demo.agrivardhak",
        locale="en-IN",
        password_hash=_demo_hash(),
        is_demo_account=True,
    )
    session.add_all([ceo, officer, admin])
    session.flush()
    session.add_all(
        [
            RoleGrant(user_id=ceo.id, organization_id=org.id, role=enums.Role.FPO_CEO),
            RoleGrant(user_id=officer.id, organization_id=org.id, role=enums.Role.FIELD_OFFICER),
            RoleGrant(user_id=admin.id, organization_id=None, role=enums.Role.PLATFORM_ADMIN),
        ]
    )
    session.flush()


def _seed_announcements(session: Session, org: Organization) -> int:
    """Organization notices, deliberately mixed in visibility (FR-105, INV-5).

    Three shared with members and two kept internal, and the internal pair is the important
    half. INV-5 is easy to *claim* when there is nothing on the other side of the boundary;
    it is only demonstrable when the collective is genuinely holding information a farmer
    cannot see, and the farmer assistant declines to reveal it while still showing what it
    can. A boundary with nothing behind it proves nothing.

    ⚠️ SYNTHETIC — DEMO ONLY. Operational notices, not agronomic or scheme guidance, so no
    citation is owed under CLAUDE.md §5; no official deadline or price is asserted here.
    """
    if (
        session.execute(select(Announcement).where(Announcement.organization_id == org.id).limit(1))
        .scalars()
        .first()
    ):
        return 0

    notices: list[tuple[str, str, enums.VisibilityScope]] = [
        (
            "Paddy collection centre timings",
            "The Jhunsi collection centre will accept member paddy from 7am to 4pm on "
            "weekdays this season. Bring your membership number. Grading happens at "
            "intake, so lots are weighed and graded in front of you. (DEMO DATA)",
            enums.VisibilityScope.SHARED_WITH_MEMBERS,
        ),
        (
            "Soil health camp at the Doab block office",
            "A soil testing camp for members with plots in the Doab tract. Samples are "
            "taken free of charge and results are recorded against your plot. (DEMO DATA)",
            enums.VisibilityScope.SHARED_WITH_MEMBERS,
        ),
        (
            "Crop insurance enrolment support",
            "The field officer team is available to help members complete crop insurance "
            "paperwork. Check your own scheme list in this app for what applies to your "
            "holding — enrolment windows are set by the scheme, not by us. (DEMO DATA)",
            enums.VisibilityScope.SHARED_WITH_MEMBERS,
        ),
        (
            "Buyer negotiation position — Ganga Cold Store",
            "Internal only. Our walk-away price and the counter-offer schedule for the "
            "potato lot. Not to be shared with members while the negotiation is open: a "
            "disclosed floor is not a floor. (DEMO DATA)",
            enums.VisibilityScope.ORG_INTERNAL,
        ),
        (
            "Working capital position and disbursement sequencing",
            "Internal only. Current working capital against this season's committed input "
            "purchases, and the order in which tracts are funded if the shortfall persists. "
            "(DEMO DATA)",
            enums.VisibilityScope.ORG_INTERNAL,
        ),
    ]

    for title, body, visibility in notices:
        session.add(
            Announcement(organization_id=org.id, title=title, body=body, visibility=visibility)
        )
    session.flush()
    return len(notices)


def _demo_hash() -> str:
    from agrivardhak.api.login import DEMO_PASSWORD
    from agrivardhak.api.passwords import hash_password

    return hash_password(DEMO_PASSWORD)


def _seed_farmer_login(session: Session, org: Organization, farmers: list[Farmer]) -> None:
    """One farmer who can sign in, for the boundary demo.

    Picked rather than random: the account is more convincing when the person behind it has
    plots, an active crop and a lot contribution to look at. A farmer whose page is empty
    demonstrates the boundary just as well and reads as a bug.
    """
    with_land = session.execute(
        select(Farmer.id, Farmer.full_name)
        .join(Farm, Farm.operator_farmer_id == Farmer.id)
        .join(Plot, Plot.farm_id == Farm.id)
        .join(CropCycle, CropCycle.plot_id == Plot.id)
        .where(CropCycle.status == enums.CropCycleStatus.GROWING)
        .limit(1)
    ).first()
    farmer_id, farmer_name = with_land if with_land else (farmers[0].id, farmers[0].full_name)

    user = User(
        display_name=f"{farmer_name} — Member",
        email="farmer@demo.agrivardhak",
        locale="hi-IN",
        farmer_id=farmer_id,
        password_hash=_demo_hash(),
        is_demo_account=True,
    )
    session.add(user)
    session.flush()
    session.add(RoleGrant(user_id=user.id, organization_id=org.id, role=enums.Role.FARMER))
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
            # Skewed recent: an active season gets visited, and a uniform 0-25 day spread
            # made most readings older than their own freshness window.
            observed_at=NOW - dt.timedelta(days=min(rng.randint(0, 12), rng.randint(0, 12))),
            recorded_at=NOW - dt.timedelta(days=min(rng.randint(0, 12), rng.randint(0, 12))),
            reported_confidence=rng.uniform(0.55, 0.9)
            if source_type is enums.SourceType.AI_INFERENCE
            else None,
        )
        count += 1

    count += _seed_symptom_reports(session, cycles, sources, rng)

    session.flush()
    return count, len(discrepancy_ids)


#: Symptom pictures a field officer might actually record, per crop. The first entry in each
#: pair is a clean single-condition picture; the second is deliberately ambiguous between two
#: conditions, so FR-524's refusal-to-guess path is exercised by the seed rather than only by
#: a unit test. A demo where the system never has to say "I cannot tell" would be hiding the
#: most trustworthy thing it does.
SYMPTOM_PICTURES: dict[str, list[tuple[str, ...]]] = {
    "Potato": [
        ("leaf_lesion_dark", "white_growth_underside", "rapid_spread"),
        ("leaf_lesion_dark", "leaf_margin_necrosis"),
        ("leaf_yellowing", "lower_leaves_first"),
        ("concentric_rings", "lower_leaves_first", "leaf_lesion_dark"),
    ],
    "Wheat": [
        ("yellow_stripes", "powder_on_leaf"),
        ("leaf_yellowing", "lower_leaves_first"),
        ("leaf_yellowing",),
    ],
    "Paddy": [
        ("leaf_margin_necrosis", "wavy_lesion_edge"),
        ("leaf_yellowing", "stunted_growth"),
    ],
    "Mustard": [("leaf_yellowing", "lower_leaves_first"), ("wilting", "leaf_curl")],
    "Guava": [("wilting", "leaf_curl")],
}

#: Share of active cycles carrying a symptom report. Most fields are fine most of the time,
#: and a seed where every plot is diseased would make the outbreak signal meaningless.
SYMPTOMATIC_SHARE = 0.09


def _seed_symptom_reports(
    session: Session,
    cycles: list[CropCycle],
    sources: dict[str, DataSource],
    rng: random.Random,
) -> int:
    """Symptom checklists on a minority of active cycles, clustered in a few villages.

    Clustered rather than uniform on purpose. A uniform sprinkle would never trip the
    outbreak detector, and an outbreak signal that has never fired on the seed is a feature
    nobody has actually seen work.
    """
    active = [c for c in cycles if c.status is enums.CropCycleStatus.GROWING]
    if not active:
        return 0

    crop_by_variety = {
        variety_id: crop_name
        for variety_id, crop_name in session.execute(
            select(Variety.id, Crop.name).join(Crop, Variety.crop_id == Crop.id)
        ).all()
    }
    plot_to_farmer = {
        plot_id: (village or "")
        for plot_id, village in session.execute(
            select(Plot.id, Farmer.village)
            .join(Farm, Plot.farm_id == Farm.id)
            .join(Farmer, Farm.operator_farmer_id == Farmer.id)
        ).all()
    }

    # Pick a few villages to be the outbreak, then bias selection toward them.
    villages = sorted({v for v in plot_to_farmer.values() if v})
    hot = set(rng.sample(villages, min(3, len(villages)))) if villages else set()

    count = 0
    for cycle in active:
        village = plot_to_farmer.get(cycle.plot_id, "")
        chance = SYMPTOMATIC_SHARE * (4.0 if village in hot else 0.6)
        if rng.random() > chance:
            continue
        crop_name = crop_by_variety.get(cycle.variety_id)
        pictures = SYMPTOM_PICTURES.get(crop_name or "")
        if not pictures:
            continue
        source_key, source_type = rng.choices(
            [
                ("field-officer", enums.SourceType.FIELD_OFFICER),
                ("farmer-app", enums.SourceType.FARMER_SELF_REPORT),
            ],
            weights=[70, 30],
        )[0]
        resolver.record_observation(
            session,
            subject_type="crop_cycle",
            subject_id=cycle.id,
            attribute="symptoms",
            value_text=",".join(rng.choice(pictures)),
            source_type=source_type,
            source=sources[source_key],
            observed_at=NOW - dt.timedelta(days=rng.randint(0, 14)),
            recorded_at=NOW - dt.timedelta(days=rng.randint(0, 14)),
        )
        count += 1
    return count


#: Livestock and compost on a share of farms. Without these the Farm module cannot show the
#: integrated-farming credit, which is the term that most distinguishes a mixed smallholding
#: from a spreadsheet's view of it (D-15).
LIVESTOCK_SHARE = 0.42
COMPOST_SHARE = 0.18


def _seed_farm_resources(session: Session, rng: random.Random) -> int:
    count = 0
    for farm_row in session.execute(select(Farm)).scalars():
        if rng.random() < LIVESTOCK_SHARE:
            session.add(
                FarmResource(
                    farm_id=farm_row.id,
                    type=enums.FarmResourceType.LIVESTOCK,
                    label="Cattle / buffalo",
                    quantity=float(rng.choice([1, 1, 2, 2, 3, 4])),
                    unit="head",
                    attributes={"is_synthetic": True},
                )
            )
            count += 1
        if rng.random() < COMPOST_SHARE:
            session.add(
                FarmResource(
                    farm_id=farm_row.id,
                    type=enums.FarmResourceType.COMPOST,
                    label="Compost pit",
                    quantity=float(rng.choice([1, 1, 2])),
                    unit="pit",
                    attributes={"is_synthetic": True},
                )
            )
            count += 1
    session.flush()
    return count


# --------------------------------------------------------------------------- lots & offers

#: Where each buyer sits relative to the mandi modal price, and why. Multipliers, not
#: absolute rupees — so the seed tracks the real market instead of drifting away from it
#: (docs/DEMO-CONTEXT.md §6.2).
BUYER_PRICING: dict[str, tuple[float, str]] = {
    "Ganga Cold Store Aggregator": (1.00, "pays the mandi rate, close by, settles fast"),
    "Kanpur Wholesale Traders": (1.13, "pays above the rate to pull volume 180 km"),
    "Northern Foods Processing": (1.07, "premium for Grade A, but rejects off-spec"),
    "Handia Rice Mill": (1.02, "local miller, reliable"),
    "Govt Procurement Centre": (1.05, "MSP-linked"),
    "Meja Oil Mill": (1.01, "the Yamuna-par outlet"),
    "Sangam Premium Fruit Traders": (1.18, "GI guava premium"),
    "Metro E-Commerce Sourcing": (1.15, "pays well, rejects hard, pays late"),
}

#: Which buyers bid for which crop.
BUYER_CROPS: dict[str, tuple[str, ...]] = {
    "Ganga Cold Store Aggregator": ("Potato",),
    "Kanpur Wholesale Traders": ("Potato", "Onion"),
    "Northern Foods Processing": ("Potato",),
    "Handia Rice Mill": ("Paddy", "Rice"),
    "Govt Procurement Centre": ("Wheat", "Paddy"),
    "Meja Oil Mill": ("Mustard",),
    "Sangam Premium Fruit Traders": ("Guava",),
    "Metro E-Commerce Sourcing": ("Guava", "Tomato"),
}

#: Agmarknet commodity names differ from our crop names in one place.
AGMARKNET_NAME = {"Paddy": "Paddy(Common)"}


def _seed_lots(
    session: Session, org: Organization, cycles: list[CropCycle], rng: random.Random
) -> list[Lot]:
    """Aggregate harvested crop cycles into sellable lots.

    Lots are grouped by crop, which is what an FPO actually does — the whole point of the
    collective is that 400 scattered smallholdings become one consignment a serious buyer
    will talk to. ``LotItem`` keeps each farmer's contribution, so a share dispute stays
    resolvable and the farmer can see their own produce in the match (FR-546).
    """
    harvested = [c for c in cycles if c.status is enums.CropCycleStatus.CLOSED]
    if not harvested:
        return []

    crops_by_id = {c.id: c for c in session.execute(select(Crop)).scalars()}
    varieties = list(session.execute(select(Variety)).scalars())
    variety_crop = {v.id: crops_by_id[v.crop_id] for v in varieties if v.crop_id in crops_by_id}
    variety_yield = {v.id: float(v.base_yield_kg_per_ha or 0) for v in varieties}
    plot_farmer = {
        plot.id: farm.operator_farmer_id
        for plot, farm in session.execute(
            select(Plot, Farm).join(Farm, Plot.farm_id == Farm.id)
        ).all()
    }

    by_crop: dict[str, list[CropCycle]] = {}
    for cycle in harvested:
        crop = variety_crop.get(cycle.variety_id)
        if crop is not None:
            by_crop.setdefault(crop.name, []).append(cycle)

    lots: list[Lot] = []
    for crop_name, crop_cycles in by_crop.items():
        crop = next(c for c in crops_by_id.values() if c.name == crop_name)
        # Most recent season only — older harvests are history, not inventory.
        latest_year = max(c.season_year for c in crop_cycles)
        current = [c for c in crop_cycles if c.season_year == latest_year][:400]
        if not current:
            continue

        grade = rng.choices(["A", "B"], weights=[70, 30])[0]
        lot = Lot(
            organization_id=org.id,
            crop_id=crop.id,
            label=f"{crop_name} {latest_year} aggregate",
            quantity_kg=Decimal("0"),
            grade=grade,
            ready_date=max(
                (c.actual_harvest_date for c in current if c.actual_harvest_date),
                default=TODAY,
            ),
            origin_location=ref.ORG_DISTRICT,
        )
        session.add(lot)
        session.flush()

        total = Decimal("0")
        for cycle in current:
            farmer_id = plot_farmer.get(cycle.plot_id)
            if farmer_id is None:
                continue
            # Contribution = area x the variety's base yield. Crude — it applies the same
            # yield to every plot regardless of health, water or weather, which is exactly
            # what the Quality module (M6) exists to fix. But using the per-variety
            # coefficient rather than one flat number keeps the ratios between crops
            # honest: paddy at ~4,200 kg/ha does not produce potato-sized tonnage.
            base_yield = variety_yield.get(cycle.variety_id) or 0
            if base_yield <= 0:
                continue
            contribution = (Decimal(str(cycle.area_sqm)) / Decimal("10000")) * Decimal(
                str(base_yield)
            )
            contribution = contribution.quantize(Decimal("0.001"))
            session.add(
                LotItem(
                    lot_id=lot.id,
                    crop_cycle_id=cycle.id,
                    farmer_id=farmer_id,
                    quantity_kg=contribution,
                    grade=grade,
                )
            )
            total += contribution

        lot.quantity_kg = float(total)
        lots.append(lot)
    session.flush()
    return lots


def _seed_offers(session: Session, org: Organization, lots: list[Lot], rng: random.Random) -> int:
    """Buyer offers, anchored to the real mandi modal price for each crop.

    Prices are multipliers on what the crop actually traded at (``BUYER_PRICING``), never
    absolute rupees. A crop with no price in the loaded window gets **no offer** rather than
    an invented one — an FPO shown a fabricated bid is worse off than one shown nothing.
    """
    buyers = list(session.execute(select(Buyer).where(Buyer.organization_id == org.id)).scalars())
    crops = {c.id: c.name for c in session.execute(select(Crop)).scalars()}
    created = 0

    for lot in lots:
        crop_name = crops.get(lot.crop_id)
        if crop_name is None:
            continue
        anchor = latest_modal_paise_per_kg(
            session, commodity_name=AGMARKNET_NAME.get(crop_name, crop_name)
        )
        if anchor is None:
            continue
        modal, _evidence = anchor

        for buyer in buyers:
            if crop_name not in BUYER_CROPS.get(buyer.name, ()):
                continue
            multiplier, _why = BUYER_PRICING.get(buyer.name, (1.0, ""))
            # A little jitter so the demo is not suspiciously tidy, but deterministic.
            price = round(modal * multiplier * rng.uniform(0.98, 1.02))
            session.add(
                DemandSignal(
                    organization_id=org.id,
                    buyer_id=buyer.id,
                    crop_id=lot.crop_id,
                    quantity_kg=buyer.max_quantity_kg,
                    grade=buyer.quality_requirement or lot.grade,
                    price_paise_per_kg=price,
                    window_start=lot.ready_date,
                    window_end=(lot.ready_date + dt.timedelta(days=45)) if lot.ready_date else None,
                    confidence=0.7,
                )
            )
            created += 1
    session.flush()
    return created
