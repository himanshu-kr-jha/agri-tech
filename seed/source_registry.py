#!/usr/bin/env python3
"""The source registry — every external source we fetch, declared in one place.

`CLAUDE.md` forbids hardcoding URLs through the application, and `docs/DATA-SOURCING.md` §5
settles the shape: a minimal registry carrying licence, cadence and retrieval fields, with
**no scheduler**. Adding a source is adding a row here; nothing else should name a URL.

Two distinctions this file exists to keep straight:

* **publisher vs access route.** DES/CACP *authored* the cost tables; `api.data.gov.in` is
  merely where we fetched them. Recording the access route as the publisher would overstate
  data.gov.in's authority and lose the real citation.
* **authoritative vs advisory** (ADR-0012). A CACP state survey may enter a ranked margin
  comparison. A single-district university study may not — it can inform a suggestion. Both
  are *sourced*; only one is comparable.

Licence is ``UNKNOWN`` until a human confirms it. Under ADR-0014 that blocks any confidence
cap from lifting, so an unconfirmed licence makes data inert rather than merely undocumented.
"""

from __future__ import annotations

import dataclasses
import enum


class Domain(enum.StrEnum):
    """Which scraper owns a source. One scraper per domain (DATA-SOURCING.md §6)."""

    MSP = "msp"
    COST_OF_CULTIVATION = "cost_of_cultivation"
    SCHEME = "scheme"
    VARIETY = "variety"
    PRICE = "price"
    PRODUCTION = "production"
    PROCUREMENT = "procurement"


class Authority(enum.StrEnum):
    """ADR-0012. Gates whether a value may enter a ranked comparison."""

    AUTHORITATIVE = "authoritative"
    ADVISORY = "advisory"


#: Recheck cadence in days, by domain (DATA-SOURCING.md §Cadence). MSP is quarterly and
#: flagged event-driven: the CACP announcement is the event, and a quarterly poll catches it
#: within the season without pretending we can predict the date.
CADENCE_DAYS: dict[Domain, int] = {
    Domain.MSP: 90,
    Domain.COST_OF_CULTIVATION: 365,
    Domain.SCHEME: 90,
    Domain.VARIETY: 365,
    Domain.PRICE: 1,
    #: Advance estimates are revised through the year; procurement moves each season.
    Domain.PRODUCTION: 365,
    Domain.PROCUREMENT: 90,
}


@dataclasses.dataclass(frozen=True)
class Source:
    """One fetchable resource."""

    key: str
    batch: int
    domain: Domain
    title: str
    #: Who authored the data. The citation.
    publisher: str
    #: Where we actually fetch it. Never the citation.
    access_route: str
    #: data.gov.in resource uuid, or None for sources fetched by plain URL.
    resource_id: str | None = None
    url: str | None = None
    unit: str | None = None
    temporal_coverage: str | None = None
    #: Which script fetches this. "datagovin" for api.data.gov.in resources, otherwise the
    #: name of a dedicated scraper — a source is not fetchable until one exists.
    fetcher: str = "datagovin"
    #: ISO 639-1. Hindi sources are stored verbatim and never translated on ingest (ADR-0015).
    language: str = "en"
    #: Server-side filters, applied as ``filters[key]=value``. Scoping to UP at the API keeps
    #: a 246k-row national series down to the 33k rows we actually reason over.
    filters: dict[str, str] | None = None
    authority: Authority = Authority.AUTHORITATIVE
    #: ``UNKNOWN`` blocks a cap lift (ADR-0014). Never guess this.
    licence: str = "UNKNOWN"
    notes: str = ""

    @property
    def cadence_days(self) -> int:
        return CADENCE_DAYS[self.domain]

    @property
    def batch_dir(self) -> str:
        return f"batch{self.batch}_{self.domain.value}"


_DES = "Directorate of Economics & Statistics / CACP, Ministry of Agriculture & Farmers Welfare"
_DGI = "api.data.gov.in"


SOURCES: list[Source] = [
    # ---------------------------------------------------------------- batch 1 — MSP
    # Promoted ahead of cost of cultivation because it came back current to 2025-26 while the
    # cost series stops at 2017-18, and because the system cannot presently distinguish MSP
    # announced from procurement price from market price from effective realization.
    Source(
        key="msp-rabi",
        batch=1,
        domain=Domain.MSP,
        title="Rabi crop-wise MSP and cost of production",
        publisher=_DES,
        access_route=_DGI,
        resource_id="6f655085-856d-4246-a516-5d6b3bebb990",
        unit="INR per quintal",
        temporal_coverage="2022-23..2025-26",
        notes="Current. Wheat, Barley, Gram, Masur, Rapeseed/Mustard, Safflower.",
    ),
    Source(
        key="msp-kharif",
        batch=1,
        domain=Domain.MSP,
        title="Kharif crop-wise MSP and cost of production",
        publisher=_DES,
        access_route=_DGI,
        resource_id="aa823ea9-ecb3-45ea-9ec0-1fcb0c522feb",
        unit="INR per quintal",
        temporal_coverage="2021-22..2024-25",
        notes="Current. 17 rows incl. paddy grades and cotton staples.",
    ),
    # ------------------------------------------------- batch 2 — cost of cultivation
    # These are AGGREGATES. They do not retire E1-E6, which needs six per-hectare components
    # (farm.py: "a single 'cost of cultivation' number cannot answer 'what if we are short of
    # cash in October'"). They bound it instead: a synthetic component set whose total, divided
    # by yield, lands far from the real A2+FL is provably wrong. The itemised tables live on
    # desagri.gov.in, unreachable at time of writing; MoSPI 4.12 is the untried route.
    Source(
        key="coc-a2fl",
        batch=2,
        domain=Domain.COST_OF_CULTIVATION,
        title="State-wise and crop-wise cost of production (A2+FL), important crops",
        publisher=_DES,
        access_route=_DGI,
        resource_id="a24e6a66-32d3-46a0-a5c3-7bcfd58d6e02",
        unit="INR per quintal",
        temporal_coverage="2013-14..2017-18",
        notes="Stale. Aggregate only — no component breakdown. UP covers exactly 15 crops.",
    ),
    Source(
        key="coc-c2",
        batch=2,
        domain=Domain.COST_OF_CULTIVATION,
        title="State-wise and crop-wise cost of production (C2), important crops",
        publisher=_DES,
        access_route=_DGI,
        resource_id="dc3ba615-2892-49c6-bdcd-ecdf0d24c8a5",
        unit="INR per quintal",
        temporal_coverage="2013-14..2017-18",
        notes="Stale. Aggregate only. C2 includes imputed rent and interest on owned capital.",
    ),
    # -------------------------------------------------- batch 3 — UP schemes (Hindi)
    # Uttar Pradesh government orders for the Agriculture department. Hindi, official, public,
    # and carrying no personal data. This is the route to the state schemes seed/sources.md §7
    # lists as S9-S12, which are published in Hindi and largely nowhere else.
    #
    # NOT used, deliberately: agridarshan.up.gov.in/api/. Reading its Angular bundle found the
    # API, and the endpoints are beneficiaryMgt/getBenfById, farmerRegister/getVerifier,
    # grantWiseBill/getFarmerList and similar — an internal DBT beneficiary administration
    # system holding personal farmer records. Technically reachable, and out of bounds under
    # INV-9 and the project's own rule against collecting personal farmer data.
    Source(
        key="up-go-agriculture",
        batch=3,
        domain=Domain.SCHEME,
        title="Uttar Pradesh government orders — Agriculture department (शासनादेश)",
        publisher="Government of Uttar Pradesh, Department of Agriculture",
        access_route="shasanadesh.up.gov.in",
        url="https://shasanadesh.up.gov.in/ShowGOforDept.aspx?dept=37",
        fetcher="up_schemes",
        language="hi",
        temporal_coverage="rolling; newest first",
        licence=(
            "Non-commercial research and private study, with attribution; any other re-use "
            "requires department permission (shasanadesh.up.gov.in Copyright Policy). "
            "COMMERCIAL USE NOT CLEARED."
        ),
        notes=(
            "ASP.NET GridView, 25 rows per page, paginated by __doPostBack with VIEWSTATE. "
            "Hindi is canonical and stored verbatim (ADR-0015)."
        ),
    ),
    # ------------------------------------------------------- batch 4 — crop varieties
    Source(
        key="variety-field-crops",
        batch=4,
        domain=Domain.VARIETY,
        title="Field crop varieties and hybrids released and notified",
        publisher="Indian Council of Agricultural Research / Ministry of Agriculture",
        access_route=_DGI,
        resource_id="53cd4900-a5ee-45e0-bc2e-56a288a6a2fd",
        temporal_coverage="2008..2012",
        notes=(
            "255 rows with actual variety names by crop and year. The companion NARS dataset "
            "(9cac7b14) holds only counts, and the horticultural one (46f587a9) is 13 rows of "
            "mostly NA with no guava — neither is registered."
        ),
    ),
    # ------------------------------------- batch 5 — crop production, area and yield
    # The most valuable single source found. District x season x crop x year, with area AND
    # production, so yield is derivable. Bears directly on seed/sources.md A1-A4 (base yield,
    # all TODO). Scoped to UP: 33,306 rows of a 246,091-row national series.
    #
    # Entity-resolution trap, recorded because it silently returns nothing: the district is
    # ALLAHABAD, not PRAYAGRAJ. The series predates the 2018 rename and a join on the current
    # name matches zero rows.
    Source(
        key="crop-production-district",
        batch=5,
        domain=Domain.PRODUCTION,
        title="District-wise, season-wise crop production statistics",
        publisher="Ministry of Agriculture & Farmers Welfare",
        access_route=_DGI,
        resource_id="35be999b-0208-4354-b557-f6ca9a5355de",
        unit="area in hectares, production in tonnes",
        temporal_coverage="1997..2014",
        filters={"state_name": "Uttar Pradesh"},
        notes=(
            "Allahabad (= Prayagraj) has 470 rows across 38 crops. District mean yields "
            "2007-14: wheat ~2.3, paddy ~2.4, potato ~16.3 t/ha. 2014 is an outlier low year "
            "and should not be read alone."
        ),
    ),
    # ------------------------------------------------------------ batch 6 — procurement
    # Domain 3 of the original brief, previously unaddressed entirely.
    Source(
        key="procurement-wheat-paddy",
        batch=6,
        domain=Domain.PROCUREMENT,
        title="Procurement of wheat and paddy, MSP value and farmers benefited",
        publisher="Department of Food & Public Distribution / FCI",
        access_route=_DGI,
        resource_id="f8340bd2-2b3c-4049-84bd-89da9f98d76a",
        unit="quantity in LMT, value in INR crore, farmers as a count",
        temporal_coverage="2018-19..2022-23",
        notes="Carries farmers_benefited: 4,033,463 wheat farmers in 2018-19.",
    ),
    Source(
        key="procurement-paddy-statewise",
        batch=6,
        domain=Domain.PROCUREMENT,
        title="State/UT-wise paddy procurement and value at MSP",
        publisher="Department of Food & Public Distribution",
        access_route=_DGI,
        resource_id="e10ca3fd-2577-4f45-8b7c-2e0ae0fcf95e",
        unit="quantity in LMT, value in INR crore",
        temporal_coverage="Apr-Jun 2021",
        notes="23 states. Narrow window, but the only state-wise procurement split found.",
    ),
    # ------------------------------------ batch 3 addition — UP public CMS (bilingual)
    # The ONE public endpoint on agridarshan. Its reference endpoints (getDistrict, getBlock,
    # administrative/getByCode, agency/getAll) all return 403: authentication-gated, therefore
    # not public data, and a 403 is an access control we do not work around. Its beneficiary
    # endpoints are personal data and are never touched. cms/getAll needs no auth and carries
    # 69 circulars, 24 bilingual FAQs, advisories and announcements. No Aadhaar/IFSC present.
    Source(
        key="up-agridarshan-cms",
        batch=3,
        domain=Domain.SCHEME,
        title="UP Agriculture department public CMS — circulars, advisories, FAQs",
        publisher="Government of Uttar Pradesh, Department of Agriculture",
        access_route="agridarshan.up.gov.in",
        url="https://agridarshan.up.gov.in/api/cms/getAll",
        fetcher="up_schemes",
        language="hi",
        authority=Authority.ADVISORY,
        temporal_coverage="rolling",
        notes=(
            "Advisory tier: FAQs and circulars are guidance, not the eligibility text a rule "
            "may be transcribed from. Bilingual fields; Hindi remains canonical (ADR-0015)."
        ),
    ),
]


def by_key(key: str) -> Source:
    for source in SOURCES:
        if source.key == key:
            return source
    raise KeyError(f"no source registered with key {key!r}")


def in_batch(batch: int) -> list[Source]:
    return [s for s in SOURCES if s.batch == batch]


def batches() -> list[int]:
    return sorted({s.batch for s in SOURCES})
