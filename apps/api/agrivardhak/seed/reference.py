"""Reference data for the Prayagraj demo (docs/DEMO-CONTEXT.md).

Every value here is either **verified** against a primary source and cited in
`seed/sources.md`, or explicitly **synthetic**. There is no third category: a number without
a citation is marked `is_synthetic=True` and renders with the DEMO DATA badge (UI-04, C-2).

Where an agronomic coefficient is still unsourced it carries ``source_ref=None`` and the
variety is flagged synthetic — so the UI tells the truth about it even before `seed/sources.md`
row A1-A13 is filled in.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agrivardhak.domain.enums import OrgResourceType, Season, SourceType

# --------------------------------------------------------------------------- district

#: Verified against prayagraj.nic.in, 2026-08-22 (seed/sources.md G3).
#: 8 tehsils, 23 development blocks.
TEHSIL_BLOCKS: dict[str, list[str]] = {
    "Sadar": ["Sadar"],
    "Soraon": [
        "Kaurihar",
        "Holagarh",
        "Mauaima",
        "Soraon",
        "Shringverpur Dham",
        "Bhagwatpur",
    ],
    "Phulpur": ["Bahariya", "Phulpur", "Bahadurpur", "Sahson"],
    "Handia": ["Pratappur", "Saidabad", "Dhanupur", "Handia"],
    "Karchhana": ["Chaka", "Karchhana", "Kaundhiyara"],
    "Bara": ["Jasra", "Shankargarh"],
    "Meja": ["Uruwa", "Meja", "Manda"],
    "Koraon": ["Koraon"],
}

#: Tehsil → tract. Still a judgement call at block level (seed/sources.md G3b) — the tract
#: assignment drives where risk clusters, so confirm against the district map before the
#: demo claims geographic precision.
TEHSIL_TRACT: dict[str, str] = {
    "Soraon": "GANGA_PAR",
    "Phulpur": "GANGA_PAR",
    "Handia": "GANGA_PAR",
    "Sadar": "DOAB",
    "Karchhana": "DOAB",
    "Bara": "YAMUNA_PAR",
    "Meja": "YAMUNA_PAR",
    "Koraon": "YAMUNA_PAR",
}


@dataclass(frozen=True)
class TractProfile:
    """What differs between the three tracts — the reason risk clusters at all."""

    key: str
    label: str
    farmer_share: float
    irrigation_coverage: float
    soil_type: str
    #: Multiplier on base yield. Vindhyan soils are shallower and largely rain-fed.
    yield_factor: float
    #: Weight for weather exposure in the Risk module.
    rainfall_exposure: float


TRACTS: dict[str, TractProfile] = {
    "GANGA_PAR": TractProfile("GANGA_PAR", "Ganga-par", 0.42, 0.85, "Alluvial", 1.00, 0.25),
    "DOAB": TractProfile("DOAB", "Doab", 0.33, 0.78, "Alluvial", 0.98, 0.35),
    "YAMUNA_PAR": TractProfile("YAMUNA_PAR", "Yamuna-par", 0.25, 0.31, "Red/lateritic", 0.72, 0.80),
}


# --------------------------------------------------------------------------- landholding

#: docs/DEMO-CONTEXT.md §5.1. Targets 976.2 ha ≈ 2,412 acres across 1,000 farmers.
#: The shape (marginal-dominant) reflects eastern UP; the exact means are synthetic until
#: seed/sources.md L1 is filled from the Agriculture Census.
HOLDING_CLASSES: list[tuple[str, int, float]] = [
    ("MARGINAL", 640, 0.55),
    ("SMALL", 260, 1.32),
    ("SEMI_MEDIUM", 88, 2.60),
    ("MEDIUM", 12, 4.35),
]

TARGET_TOTAL_HA = 976.2


# --------------------------------------------------------------------------- markets

#: Verified 2026-08-22 from api.agmarknet.gov.in/v1/market-district-state (sources.md M1).
#: These are the real Agmarknet keys. "Mundera Mandi" is NOT one of them — the key for that
#: site is Prayagraj APMC. Do not add invented names here.
AGMARKNET_MARKETS: list[tuple[int, str, str, str | None]] = [
    (298, "Prayagraj APMC", "Principal Market Yard", None),
    (1724, "Ajuha APMC", "Principal Market Yard", None),
    (1749, "Sirsa APMC", "Principal Market Yard", "Meja"),
    (1764, "Jasra APMC", "Principal Market Yard", "Bara"),
    (4389, "Lediyari APMC", "Other", None),
]

AGMARKNET_DISTRICT_ID = 646
AGMARKNET_STATE_ID = 34


# --------------------------------------------------------------------------- crops


@dataclass(frozen=True)
class VarietySpec:
    name: str
    duration_days: int | None
    base_yield_kg_per_ha: float | None
    water_requirement_mm: float | None
    #: Citation in seed/sources.md. None => synthetic, and the UI must say so.
    source_ref: str | None = None


@dataclass(frozen=True)
class CropSpec:
    name: str
    name_hi: str
    season: Season
    is_perennial: bool
    agmarknet_commodity_id: int | None
    #: Which tracts it is grown in, for the seed's plausibility.
    tracts: tuple[str, ...]
    varieties: list[VarietySpec] = field(default_factory=list)


#: The five demo crops (docs/DEMO-CONTEXT.md §4). Yield figures are SYNTHETIC placeholders
#: pending seed/sources.md A1-A5; every variety below therefore carries source_ref=None and
#: is seeded with is_synthetic=True.
CROPS: list[CropSpec] = [
    CropSpec(
        "Paddy",
        "धान",
        Season.KHARIF,
        False,
        2,
        ("GANGA_PAR", "DOAB"),
        [VarietySpec("Sarjoo-52", 135, 4200, 1200), VarietySpec("Swarna", 145, 4500, 1250)],
    ),
    CropSpec(
        "Wheat",
        "गेहूँ",
        Season.RABI,
        False,
        1,
        ("GANGA_PAR", "DOAB", "YAMUNA_PAR"),
        [VarietySpec("HD-2967", 145, 4000, 450), VarietySpec("DBW-187", 140, 4300, 450)],
    ),
    CropSpec(
        "Potato",
        "आलू",
        Season.RABI,
        False,
        24,
        ("DOAB", "GANGA_PAR"),
        [
            VarietySpec("Kufri Bahar", 110, 25000, 600),
            VarietySpec("Kufri Chipsona", 100, 23000, 600),
        ],
    ),
    CropSpec(
        "Mustard",
        "सरसों",
        Season.RABI,
        False,
        12,
        ("YAMUNA_PAR", "DOAB"),
        [VarietySpec("Varuna", 130, 1400, 250), VarietySpec("Pusa Bold", 125, 1600, 250)],
    ),
    CropSpec(
        "Guava",
        "अमरूद",
        Season.PERENNIAL,
        True,
        156,
        ("GANGA_PAR",),
        [
            # Quality spec IS verified — GI Journal 19, Oct 2007, application no. 50
            # (seed/sources.md Q1-Q3). 120 kg/tree in the 6th year; ~250 trees/ha.
            VarietySpec(
                "Allahabad Surkha",
                None,
                30000,
                800,
                source_ref="GI Journal No. 19 (Oct 2007), application no. 50",
            ),
        ],
    ),
]

#: Blocks inside the registered Allahabad Surkha GI area that fall in present-day Prayagraj
#: (seed/sources.md Q2). Both are Ganga-par. Guava plots are placed only here.
GI_GUAVA_BLOCKS = ("Kaurihar", "Phulpur")


# --------------------------------------------------------------------------- data sources


@dataclass(frozen=True)
class SourceSpec:
    key: str
    label: str
    source_type: SourceType
    base_trust: float
    url: str | None
    is_fixture: bool


DATA_SOURCES: list[SourceSpec] = [
    SourceSpec("field-officer", "FPO field officer", SourceType.FIELD_OFFICER, 0.95, None, False),
    SourceSpec(
        "farmer-app", "Farmer self-report", SourceType.FARMER_SELF_REPORT, 0.70, None, False
    ),
    SourceSpec("org-register", "FPO member register", SourceType.ORG_RECORD, 0.90, None, False),
    SourceSpec(
        "agmarknet",
        "Agmarknet (DMI, Ministry of Agriculture)",
        SourceType.EXTERNAL_SOURCE,
        0.85,
        "https://api.agmarknet.gov.in/v1",
        False,
    ),
    SourceSpec(
        "open-meteo",
        "Open-Meteo weather archive",
        SourceType.EXTERNAL_SOURCE,
        0.85,
        "https://open-meteo.com",
        False,
    ),
    SourceSpec("vision-model", "Crop image classifier", SourceType.AI_INFERENCE, 0.75, None, False),
    SourceSpec("demo-fixture", "Synthetic demo fixture", SourceType.FIXTURE, 0.50, None, True),
]


# --------------------------------------------------------------------------- organization

ORG_NAME = "Prayagraj Kisan Producer Company Limited"
ORG_DISTRICT = "Prayagraj"
ORG_STATE = "Uttar Pradesh"

#: Synthetic. A real FPO balance sheet is not available (seed/sources.md X7).
#: Cold-storage capacity is deliberately left None — "unknown", not zero (FR-103), so the
#: orchestrator has to reason about a resource it does not know the size of.
ORG_RESOURCES: list[tuple[OrgResourceType, str, float | None, str | None, int | None]] = [
    (OrgResourceType.WORKING_CAPITAL, "Season working capital", None, None, 5_000_000_00),
    (OrgResourceType.WAREHOUSE, "Ganga-par godown", 800.0, "tonne", None),
    (
        OrgResourceType.COLD_STORAGE,
        "Contracted cold store (capacity unconfirmed)",
        None,
        "tonne",
        None,
    ),
    (OrgResourceType.VEHICLE, "Hired tractor-trailer", 3.0, "vehicle", None),
]
