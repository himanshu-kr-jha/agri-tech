"""Seed tests — DR-09 determinism and the demo's structural guarantees.

These assert the properties the demo script depends on. If one goes red, a demo beat has
silently stopped working: the headline acreage has drifted, the discrepancy badge has
nothing to show, or the guava growers have wandered out of the GI area.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from agrivardhak.domain.enums import CropCycleStatus, DiscrepancyStatus
from agrivardhak.domain.models.crops import Crop, CropCycle, Variety
from agrivardhak.domain.models.land import Farm, Plot, PlotTenure
from agrivardhak.domain.models.market import Buyer
from agrivardhak.domain.models.organization import Farmer, Membership, Organization
from agrivardhak.domain.models.provenance import DataDiscrepancy
from agrivardhak.domain.units import sqm_to_acres
from agrivardhak.seed import reference as ref

pytestmark = pytest.mark.usefixtures("db")


@pytest.fixture(scope="module")
def seeded(request) -> None:
    """Require an already-seeded database.

    The seed takes ~30s and writes through append-only triggers, so these tests read the
    database `make seed` produced rather than building their own. They skip rather than
    fail when it is absent, so `pytest` stays useful before the first seed.
    """
    from sqlalchemy import create_engine

    from agrivardhak.config import get_settings

    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        count = conn.execute(
            select(func.count()).select_from(Organization).where(Organization.name == ref.ORG_NAME)
        ).scalar_one()
    engine.dispose()
    if not count:
        pytest.skip("database not seeded — run `make seed`")


@pytest.fixture
def org(session, seeded) -> Organization:
    return (
        session.execute(select(Organization).where(Organization.name == ref.ORG_NAME))
        .scalars()
        .one()
    )


# --------------------------------------------------------------------------- headline numbers


def test_membership_is_one_thousand_farmers(session, org) -> None:
    """The demo says 1,000 farmers. It has to be 1,000 farmers."""
    count = session.execute(
        select(func.count()).select_from(Membership).where(Membership.organization_id == org.id)
    ).scalar_one()
    assert count == 1000


def test_total_area_matches_the_documented_acreage(session, seeded) -> None:
    """docs/DEMO-CONTEXT.md §5.1 promises 2,412 acres; beat 3 of the demo says it aloud."""
    total_sqm = session.execute(select(func.sum(Plot.area_sqm))).scalar_one()
    assert sqm_to_acres(float(total_sqm)) == pytest.approx(2412, abs=2)


def test_organization_is_flagged_synthetic(session, org) -> None:
    """C-2 / UI-04: nothing in this demo may present itself as real."""
    assert org.is_synthetic is True
    assert all(f.is_synthetic for f in session.execute(select(Farmer)).scalars())
    assert all(b.is_synthetic for b in session.execute(select(Buyer)).scalars())


# --------------------------------------------------------------------------- structure


def test_farmers_span_all_three_tracts(session, seeded) -> None:
    """Heterogeneity is the whole reason this district was chosen (D-24).

    Without all three tracts populated, the drill-down shows a list rather than a pattern.
    """
    tracts = {row[0] for row in session.execute(select(Farmer.tract).distinct()).all() if row[0]}
    assert tracts == {"GANGA_PAR", "DOAB", "YAMUNA_PAR"}


def test_yamuna_par_is_predominantly_rain_fed(session, seeded) -> None:
    """The risk story depends on the southern tract actually being exposed."""
    rows = session.execute(
        select(Plot.irrigation_source, Farmer.tract)
        .join(Farm, Plot.farm_id == Farm.id)
        .join(Farmer, Farm.operator_farmer_id == Farmer.id)
    ).all()
    by_tract: dict[str, list[str]] = {}
    for source, tract in rows:
        by_tract.setdefault(tract, []).append(source)

    def rainfed_share(tract: str) -> float:
        values = by_tract[tract]
        return sum(1 for v in values if v == "Rain-fed") / len(values)

    assert rainfed_share("YAMUNA_PAR") > 0.55
    assert rainfed_share("GANGA_PAR") < 0.25


def test_blocks_are_real_prayagraj_blocks(session, seeded) -> None:
    """No invented place names — the same rule as the mandi list."""
    real = {block for blocks in ref.TEHSIL_BLOCKS.values() for block in blocks}
    seeded_blocks = {
        row[0] for row in session.execute(select(Farmer.block).distinct()).all() if row[0]
    }
    assert seeded_blocks <= real


def test_guava_is_only_grown_in_the_gi_blocks(session, seeded) -> None:
    """seed/sources.md Q2: the GI's Prayagraj blocks are Kaurihar and Phulpur.

    A guava grower outside them cannot claim the Allahabad Surkha mark, so placing one
    there would make the demo's policy beat wrong.
    """
    rows = session.execute(
        select(Farmer.block)
        .select_from(CropCycle)
        .join(Variety, CropCycle.variety_id == Variety.id)
        .join(Crop, Variety.crop_id == Crop.id)
        .join(Plot, CropCycle.plot_id == Plot.id)
        .join(Farm, Plot.farm_id == Farm.id)
        .join(Farmer, Farm.operator_farmer_id == Farmer.id)
        .where(Crop.name == "Guava")
        .distinct()
    ).all()
    blocks = {row[0] for row in rows}
    assert blocks, "the demo needs at least some guava"
    assert blocks <= set(ref.GI_GUAVA_BLOCKS)


def test_there_is_history_and_an_active_season(session, seeded) -> None:
    """The learning loop (beat 12) needs closed cycles; the packet needs open ones."""
    statuses = {row[0] for row in session.execute(select(CropCycle.status).distinct()).all()}
    assert CropCycleStatus.CLOSED in statuses
    assert CropCycleStatus.GROWING in statuses


# --------------------------------------------------------------------------- demo beats


def test_open_discrepancies_exist_for_the_provenance_beat(session, seeded) -> None:
    """Beat 5 shows a plot with three conflicting area claims. It needs one to exist."""
    discrepancies = list(
        session.execute(
            select(DataDiscrepancy).where(DataDiscrepancy.status == DiscrepancyStatus.OPEN)
        ).scalars()
    )
    assert discrepancies, "no open discrepancy — the demo's provenance moment has nothing to show"

    three_way = [d for d in discrepancies if len(d.claims) >= 3]
    assert three_way, "need at least one three-way conflict (farmer / record / field officer)"

    example = three_way[0]
    sources = {c["source_type"] for c in example.claims}
    assert len(sources) >= 3, "the claims must come from genuinely different sources"
    assert float(example.spread_pct) > float(example.tolerance_pct)
    assert float(example.effective_confidence) < 0.95, "a conflict must depress confidence"


def test_tenure_conflicts_exist_and_are_visible(session, seeded) -> None:
    """ADR-0003: real land records are messy, and the system must surface the gap."""
    rows = session.execute(
        select(PlotTenure.plot_id, func.sum(PlotTenure.share_pct))
        .where(PlotTenure.valid_to.is_(None))
        .group_by(PlotTenure.plot_id)
    ).all()
    off_by = [plot_id for plot_id, total in rows if abs(float(total) - 100.0) > 0.01]
    assert off_by, "no tenure conflicts seeded — ADR-0003's messy-records case is untested"


def test_buyers_include_the_effective_price_reversal_pair(session, org) -> None:
    """Beat 7 turns on a near buyer beating a distant one on effective price."""
    buyers = list(session.execute(select(Buyer).where(Buyer.organization_id == org.id)).scalars())
    assert len(buyers) == 8

    near = min(buyers, key=lambda b: float(b.distance_km or 1e9))
    far = max(buyers, key=lambda b: float(b.distance_km or 0))
    assert float(near.distance_km) < 30
    assert float(far.distance_km) > 150
    assert (far.payment_terms_days or 0) > (near.payment_terms_days or 0), (
        "the distant buyer must also have worse terms, or the reversal is not interesting"
    )
    assert float(far.rejection_rate) > float(near.rejection_rate)


def test_every_variety_declares_whether_it_is_sourced(session, seeded) -> None:
    """A yield coefficient is either cited or flagged synthetic. No third category."""
    for variety in session.execute(select(Variety)).scalars():
        if variety.source_ref:
            assert variety.is_synthetic is False
        else:
            assert variety.is_synthetic is True, (
                f"{variety.name} has no source_ref and is not flagged synthetic"
            )


# --------------------------------------------------------------------------- learning loop


def test_the_learning_loop_is_seeded(session, org) -> None:
    """The Impact panel has something to report on a fresh seed (M18, FR-1201...1203)."""
    from agrivardhak.learning import attribution

    summary = attribution.summarise(session, organization_id=org.id)
    # Lower bounds, not equality. The suite runs against the same database `make seed`
    # populated, and other tests in it create interventions of their own — an exact count
    # here fails depending on which tests ran first, which is a property of the fixture
    # rather than of the seed.
    assert isinstance(summary["interventions"], int)
    assert summary["interventions"] >= 15
    assert isinstance(summary["attributions"], int)
    assert summary["attributions"] >= 11
    assert summary["predictions_scored"] > 0
    assert summary["mean_absolute_error"] is not None


def test_the_seeded_impact_is_not_a_highlight_reel(session, org) -> None:
    """SAF-12, asserted rather than intended.

    The screen's whole argument is that what could *not* be attributed matters as much as
    what could. A seed weighted toward successes would quietly turn it into the vendor
    dashboard it exists to argue against, and nothing else in the suite would notice.
    """
    from agrivardhak.learning import attribution

    summary = attribution.summarise(session, organization_id=org.id)
    strengths = summary["attribution_strength"]
    assert isinstance(strengths, dict)
    assert isinstance(summary["interventions"], int)

    clean_wins = strengths.get("HIGH", 0) + strengths.get("MODERATE", 0)
    assert clean_wins * 2 <= summary["interventions"], (
        f"{clean_wins} of {summary['interventions']} executed actions are clean wins. "
        "The seed has drifted into a highlight reel."
    )
    assert strengths.get("CONFOUNDED", 0) > 0, "no confounded attribution — SAF-12 unshown"
    assert strengths.get("UNCERTAIN", 0) > 0, "nothing landed inside ordinary variation"
    assert summary["unattributable"] > 0, "every action attributed — INV-7 has nothing to show"


def test_every_executed_recommendation_has_an_approval(session, org) -> None:
    """INV-1 as a property of the seeded data, not only of the API.

    The seed writes history directly rather than going through the approval endpoint, so it
    is exactly the place a recommendation could reach EXECUTED without a human behind it.
    """
    from agrivardhak.domain.enums import RecommendationStatus
    from agrivardhak.domain.models.decisions import Approval, Recommendation

    executed = list(
        session.execute(
            select(Recommendation).where(
                Recommendation.organization_id == org.id,
                Recommendation.status == RecommendationStatus.EXECUTED,
            )
        ).scalars()
    )
    assert executed, "no executed recommendations in the seed"
    for recommendation in executed:
        approvals = list(
            session.execute(
                select(Approval).where(Approval.recommendation_id == recommendation.id)
            ).scalars()
        )
        assert approvals, f"{recommendation.title!r} is EXECUTED with no approval row (INV-1)"


def test_unfollowed_advice_is_recorded_and_not_scored(session, org) -> None:
    """INV-7. Advice nobody took must leave a row saying so, and must not be attributed."""
    from agrivardhak.domain.enums import Adherence
    from agrivardhak.domain.models.decisions import Attribution, Intervention

    refused = list(
        session.execute(
            select(Intervention).where(Intervention.followed.in_([Adherence.NO, Adherence.UNKNOWN]))
        ).scalars()
    )
    assert refused, "nothing in the seed represents advice that was not followed"
    for intervention in refused:
        scored = list(
            session.execute(
                select(Attribution).where(Attribution.intervention_id == intervention.id)
            ).scalars()
        )
        assert not scored, (
            f"intervention {intervention.id} was not followed but carries an attribution — "
            "the model would learn from advice nobody took"
        )
