"""M7b — the plumbing that feeds the Market module real data.

Two things these guard. First, that prices come back out of the database with resolvable
evidence, so a recommendation can be audited to the payload we fetched. Second, that seeded
buyer offers stay anchored to what the crop actually trades at — the failure mode here is
subtle and embarrassing: an FPO shown negotiating potato at ₹30/kg when the mandi says ₹7.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import func, select

from agrivardhak.domain.models.crops import Crop, Variety
from agrivardhak.domain.models.market import Buyer, DemandSignal, Lot, LotItem
from agrivardhak.domain.models.organization import Organization
from agrivardhak.domain.models.provenance import ExternalRecord
from agrivardhak.ingestion import agmarknet
from agrivardhak.seed import reference as ref
from agrivardhak.seed.generator import AGMARKNET_NAME, BUYER_CROPS, BUYER_PRICING

pytestmark = pytest.mark.usefixtures("db")


@pytest.fixture(scope="module")
def seeded() -> None:
    from sqlalchemy import create_engine

    from agrivardhak.config import get_settings

    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        lots = conn.execute(select(func.count()).select_from(Lot)).scalar_one()
    engine.dispose()
    if not lots:
        pytest.skip("database not seeded with lots — run `make seed`")


# --------------------------------------------------------------------------- ingestion


def test_prices_are_external_records_not_observations(session, seeded) -> None:
    """A mandi price is a fact about the world, not a claim about one of our subjects.

    Storing 23,000 price rows as observations would fill a table whose purpose is
    attributing claims to farmers and plots with rows about nobody.
    """
    count = session.execute(
        select(func.count())
        .select_from(ExternalRecord)
        .where(ExternalRecord.kind == "MARKET_PRICE")
    ).scalar_one()
    assert count > 20_000


def test_price_points_carry_resolvable_evidence(session, seeded) -> None:
    """INV-2: a recommendation must be auditable down to the payload we fetched."""
    points = agmarknet.price_points(session, commodity_name="Potato", limit=50)
    assert points
    for point in points:
        assert point.evidence.kind == "external_record"
        record = session.get(ExternalRecord, point.evidence.id)
        assert record is not None, "the evidence ref must resolve to a real row"
        assert record.payload["modal_paise_per_kg"] == point.modal_paise_per_kg


def test_stored_prices_are_paise_per_kg_not_rupees_per_quintal(session, seeded) -> None:
    """The conversion that looks like a no-op (units.rupees_per_quintal_to_paise_per_kg).

    Prayagraj potato traded around ₹700/quintal in Aug 2026, which is ₹7/kg. If someone
    "fixes" the conversion by multiplying, this catches it: ₹700/kg potato is absurd.
    """
    points = agmarknet.price_points(session, commodity_name="Potato", limit=400)
    assert points
    modal = [p.modal_paise_per_kg for p in points]
    assert min(modal) > 100, "potato under ₹1/kg means the conversion divided"
    assert max(modal) < 5_000, "potato over ₹50/kg means the conversion multiplied by 100"


def test_loading_twice_inserts_nothing_the_second_time(session, seeded) -> None:
    """Append-only plus a dedupe key means re-running the loader is a no-op."""
    assert agmarknet.load_series(session) == 0


def test_unknown_commodity_returns_nothing_rather_than_guessing(session, seeded) -> None:
    assert agmarknet.price_points(session, commodity_name="Dragonfruit") == []
    assert agmarknet.latest_modal_paise_per_kg(session, commodity_name="Dragonfruit") is None


# --------------------------------------------------------------------------- lots


def test_lots_exist_for_the_demo_crops(session, seeded) -> None:
    crops = {c.id: c.name for c in session.execute(select(Crop)).scalars()}
    names = {crops[lot.crop_id] for lot in session.execute(select(Lot)).scalars()}
    assert {"Potato", "Wheat", "Paddy"} <= names


def test_lot_quantity_equals_the_sum_of_its_items(session, seeded) -> None:
    """The basis of fair settlement: a lot is exactly what its members put in."""
    for lot in session.execute(select(Lot)).scalars():
        total = session.execute(
            select(func.coalesce(func.sum(LotItem.quantity_kg), 0)).where(LotItem.lot_id == lot.id)
        ).scalar_one()
        assert float(total) == pytest.approx(float(lot.quantity_kg), rel=1e-6), (
            f"{lot.label} does not equal its contributions — a share dispute waiting to happen"
        )


def test_lot_yields_respect_per_crop_differences(session, seeded) -> None:
    """Crops do not all yield the same, and the ratios have to look right.

    An earlier draft used one flat 20,000 kg/ha for everything, which made paddy produce
    potato-sized tonnage. Mustard (~1,400 kg/ha) must stay far below potato (~25,000).
    """
    crops = {c.id: c.name for c in session.execute(select(Crop)).scalars()}
    by_crop = {
        crops[lot.crop_id]: float(lot.quantity_kg) for lot in session.execute(select(Lot)).scalars()
    }
    if "Mustard" in by_crop and "Potato" in by_crop:
        assert by_crop["Potato"] > by_crop["Mustard"] * 5


def test_guava_is_a_premium_sliver_not_a_bulk_crop(session, seeded) -> None:
    """docs/DEMO-CONTEXT.md §4.2: the documented GI area is ~73 ha, not a major crop."""
    crops = {c.id: c.name for c in session.execute(select(Crop)).scalars()}
    lots = {crops[lot.crop_id]: lot for lot in session.execute(select(Lot)).scalars()}
    if "Guava" not in lots or "Potato" not in lots:
        pytest.skip("guava or potato lot absent")
    contributors = session.execute(
        select(func.count()).select_from(LotItem).where(LotItem.lot_id == lots["Guava"].id)
    ).scalar_one()
    assert contributors < 60, "too many guava growers for a 73 ha GI area"
    assert float(lots["Guava"].quantity_kg) < float(lots["Potato"].quantity_kg)


# --------------------------------------------------------------------------- offers


def test_offers_are_anchored_to_the_real_modal_price(session, seeded) -> None:
    """The realism guard. Offers must track the market, not float free of it.

    Every buyer's price is a multiplier on the actual modal (`BUYER_PRICING`), so this
    checks each offer lands within a plausible band of what the crop really traded at.
    """
    crops = {c.id: c.name for c in session.execute(select(Crop)).scalars()}
    buyers = {b.id: b for b in session.execute(select(Buyer)).scalars()}
    signals = list(session.execute(select(DemandSignal)).scalars())
    assert signals, "no offers seeded — the Market module has nothing to rank"

    for signal in signals:
        crop_name = crops[signal.crop_id]
        anchor = agmarknet.latest_modal_paise_per_kg(
            session, commodity_name=AGMARKNET_NAME.get(crop_name, crop_name)
        )
        assert anchor is not None, f"{crop_name} offer exists without a price anchor"
        modal, _ = anchor
        multiplier, _why = BUYER_PRICING[buyers[signal.buyer_id].name]
        expected = modal * multiplier
        assert signal.price_paise_per_kg == pytest.approx(expected, rel=0.05), (
            f"{buyers[signal.buyer_id].name} offer for {crop_name} has drifted from the market"
        )


def test_no_offer_is_invented_for_a_crop_that_never_traded(session, seeded) -> None:
    """An FPO shown a fabricated bid is worse off than one shown nothing."""
    crops = {c.id: c.name for c in session.execute(select(Crop)).scalars()}
    for signal in session.execute(select(DemandSignal)).scalars():
        crop_name = crops[signal.crop_id]
        assert (
            agmarknet.latest_modal_paise_per_kg(
                session, commodity_name=AGMARKNET_NAME.get(crop_name, crop_name)
            )
            is not None
        )


def test_buyers_only_bid_for_crops_they_actually_buy(session, seeded) -> None:
    crops = {c.id: c.name for c in session.execute(select(Crop)).scalars()}
    buyers = {b.id: b for b in session.execute(select(Buyer)).scalars()}
    for signal in session.execute(select(DemandSignal)).scalars():
        buyer_name = buyers[signal.buyer_id].name
        assert crops[signal.crop_id] in BUYER_CROPS[buyer_name]


def test_potato_offers_span_the_reversal_pair(session, seeded) -> None:
    """Beat 7 needs a near-cheap and a far-dear buyer bidding on the same crop."""
    crops = {c.name: c.id for c in session.execute(select(Crop)).scalars()}
    buyers = {b.id: b for b in session.execute(select(Buyer)).scalars()}
    potato_offers = list(
        session.execute(
            select(DemandSignal).where(DemandSignal.crop_id == crops["Potato"])
        ).scalars()
    )
    assert len(potato_offers) >= 2

    distances = {
        buyers[o.buyer_id].name: float(buyers[o.buyer_id].distance_km) for o in potato_offers
    }
    assert min(distances.values()) < 30
    assert max(distances.values()) > 150


# --------------------------------------------------------------------------- reference data


def test_seeded_markets_are_the_real_agmarknet_ones(session, seeded) -> None:
    """No invented mandi names — sources.md M1."""
    real_names = {name for _id, name, _cat, _teh in ref.AGMARKNET_MARKETS}
    seen = {
        record.payload["market_name"]
        for record in session.execute(
            select(ExternalRecord).where(ExternalRecord.kind == "MARKET_PRICE").limit(500)
        ).scalars()
    }
    assert seen <= real_names, f"unexpected market names: {seen - real_names}"


def test_every_variety_yield_is_positive_or_absent(session, seeded) -> None:
    """A zero yield would silently produce empty lots rather than failing loudly."""
    for variety in session.execute(select(Variety)).scalars():
        if variety.base_yield_kg_per_ha is not None:
            assert float(variety.base_yield_kg_per_ha) > 0


def test_organization_resources_distinguish_unknown_from_zero(session, seeded) -> None:
    """FR-103. Cold-storage capacity is seeded NULL on purpose."""
    from agrivardhak.domain.models.organization import OrgResource

    org = session.execute(select(Organization)).scalars().first()
    assert org is not None
    resources = list(
        session.execute(select(OrgResource).where(OrgResource.organization_id == org.id)).scalars()
    )
    cold = [r for r in resources if r.type.value == "COLD_STORAGE"]
    assert cold and cold[0].quantity is None, (
        "cold storage must be unknown, not zero — the orchestrator has to reason about it"
    )


def test_price_history_covers_a_usable_window(session, seeded) -> None:
    """The trend finding needs enough points to say anything; below 8 it stays silent."""
    points = agmarknet.price_points(session, commodity_name="Potato", limit=800)
    assert len(points) > 100
    span = points[-1].date - points[0].date
    assert span > dt.timedelta(days=180)


def test_price_points_come_back_oldest_first(session, seeded) -> None:
    """The ordering is part of the contract, and it has already caused one bug.

    ``price_points`` returns the series **ascending** by date, so the current price is the
    *last* element. Code that read ``history[:30]`` as "the most recent 30" compared today's
    buyer offer against potato prices from two years earlier and reported a 74% realisation
    gap that did not exist — a number large enough to change a recommendation and plausible
    enough that nobody would query it.
    """
    points = agmarknet.price_points(session, commodity_name="Potato", limit=500)
    assert len(points) > 30
    dates = [p.date for p in points]
    assert dates == sorted(dates), "price_points must return the series ascending by date"
    assert points[-1].date > points[0].date


def test_the_current_price_is_the_last_point_not_the_first(session, seeded) -> None:
    """And it should agree with what the dedicated 'latest' helper says."""
    points = agmarknet.price_points(session, commodity_name="Potato", limit=2000)
    latest = agmarknet.latest_modal_paise_per_kg(session, commodity_name="Potato")
    assert latest is not None
    # Same day; the helper picks one market, the series carries several, so compare the day.
    assert points[-1].date == latest[1].as_of.date()
