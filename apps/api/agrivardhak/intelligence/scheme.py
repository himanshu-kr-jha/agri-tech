"""Scheme Intelligence — M9, FR-561…567.

Government support is the largest untapped income line for most Indian farmer collectives,
and the reason it is untapped is almost never that nobody wants it. It is that nobody knows
which of a hundred schemes they qualify for, what the deadline is, and which document they
are missing.

So this module answers three questions and refuses a fourth.

**Which schemes could this collective or this farmer claim?** Matched on recorded facts —
landholding, category, crop, tenure — not on inference. A farmer is never assessed against a
criterion we have no observation for; the assessment returns ``INSUFFICIENT_DATA`` and names
the missing fact, which is actionable in a way that a probabilistic guess is not.

**What is missing, and by when?** The gap list is the product. "You qualify" is worth little;
"you qualify, and the only thing missing is a soil health card, and the window closes on the
31st" is worth a day of a field officer's time.

**What is it worth?** Estimated, as a range, with the estimate's basis shown.

**The refusal (FR-567, SAF-11): nothing is ever submitted.** Not with a confirmation dialog,
not with a delay, not "on behalf of". The module prepares an application and a human files
it. An auto-filed government application in a farmer's name is a fraud risk that no
convenience justifies.

Two further constraints, both from the discovery session and both non-negotiable:

* **Sensitive attributes are used only for eligibility (FR-566).** A scheme reserved for SC/ST
  or women farmers requires knowing category and gender to assess it. Those same fields may
  never enter a ranking, a priority score, or a "worth investing in" judgement — and this
  module produces no per-farmer ranking at all, which is the structural way to guarantee it
  rather than a policy anyone has to remember.
* **No output ever recommends withholding support from a named farmer (FR-605, SAF-04).**

Catalog status
--------------
``SCHEMES`` holds real, named central schemes with their official portals. The *eligibility
rules encoded here are simplified and unverified* — real rules carry state amendments,
year-by-year revisions and district discretion. Every assessment therefore carries
``rules_verified=False`` and says so on screen. Verifying one scheme against its operational
guidelines lifts it (seed/sources.md S1-S12).
"""

from __future__ import annotations

import datetime as dt
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

MODULE = "scheme_intelligence"
VERSION = "1.0.0"

#: Unverified rules cannot produce a confident assessment.
UNVERIFIED_CONFIDENCE_CEILING = 0.55

#: A deadline closer than this is surfaced as urgent.
URGENT_DAYS = 45

SQM_PER_HA = Decimal(10000)


@dataclass(frozen=True)
class Criterion:
    """One testable condition.

    ``attribute`` names a fact we may or may not hold. That distinction — *fails* versus
    *cannot be assessed* — is the whole reason this is a dataclass and not a lambda.
    """

    attribute: str
    operator: str  # one of: lte, gte, eq, in, exists
    value: Any = None
    description: str = ""
    #: True where answering needs a consent-gated sensitive attribute (FR-566).
    sensitive: bool = False


@dataclass(frozen=True)
class Scheme:
    """A real scheme. Rules simplified; portal and benefit basis are real."""

    key: str
    name: str
    authority: str
    beneficiary: str  # FARMER | ORGANIZATION
    portal_url: str
    summary: str
    criteria: tuple[Criterion, ...]
    documents: tuple[str, ...]
    benefit_basis: str
    benefit_low_paise: int | None = None
    benefit_high_paise: int | None = None
    #: Month/day the window typically closes, where the scheme is seasonal. None = rolling.
    window_close: tuple[int, int] | None = None
    rules_verified: bool = False
    source_note: str = ""


SCHEMES: tuple[Scheme, ...] = (
    Scheme(
        key="pm_kisan",
        name="PM-KISAN",
        authority="Ministry of Agriculture & Farmers Welfare, Government of India",
        beneficiary="FARMER",
        portal_url="https://pmkisan.gov.in/",
        summary=(
            "Income support of Rs 6,000 a year to landholding farmer families, paid in three "
            "instalments directly to the bank account."
        ),
        criteria=(
            Criterion("is_landholder", "eq", True, "Holds cultivable land in their own name"),
            Criterion("has_aadhaar", "eq", True, "Aadhaar seeded to the bank account"),
            Criterion(
                "is_income_tax_payer", "eq", False, "Not an income-tax payer", sensitive=True
            ),
        ),
        documents=("Aadhaar", "Land record (khatauni)", "Bank account with IFSC"),
        benefit_basis="Fixed Rs 6,000 per year per family",
        benefit_low_paise=600_000,
        benefit_high_paise=600_000,
        source_note="Benefit amount is the scheme's headline figure; exclusion rules simplified.",
    ),
    Scheme(
        key="pmfby",
        name="Pradhan Mantri Fasal Bima Yojana",
        authority="Ministry of Agriculture & Farmers Welfare, Government of India",
        beneficiary="FARMER",
        portal_url="https://pmfby.gov.in/",
        summary=(
            "Crop insurance against yield loss from natural causes. Farmer premium is capped "
            "at 2% of sum insured for Kharif food crops, 1.5% for Rabi and 5% for commercial "
            "and horticultural crops; the balance is subsidised."
        ),
        criteria=(
            Criterion("has_crop_cycle", "eq", True, "Has a notified crop sown this season"),
            Criterion("has_land_record", "exists", None, "Land record or tenancy proof"),
        ),
        documents=(
            "Land record or registered tenancy agreement",
            "Sowing certificate or self-declaration",
            "Bank account",
            "Aadhaar",
        ),
        benefit_basis="Premium subsidy; payout on assessed yield loss against the threshold",
        window_close=(12, 31),
        source_note=(
            "Premium caps are the scheme's stated rates. Cut-off dates are notified per state "
            "and season and are NOT encoded here — check the portal."
        ),
    ),
    Scheme(
        key="kcc",
        name="Kisan Credit Card",
        authority="Reserve Bank of India / scheduled banks",
        beneficiary="FARMER",
        portal_url="https://www.myscheme.gov.in/schemes/kcc",
        summary=(
            "Short-term crop loan at a concessional rate, with an interest subvention and a "
            "further rebate for prompt repayment."
        ),
        criteria=(
            Criterion("is_landholder", "eq", True, "Owner-cultivator, tenant or sharecropper"),
            Criterion("has_bank_account", "eq", True, "Operative bank account"),
        ),
        documents=("Land record or tenancy proof", "Identity and address proof", "Photograph"),
        benefit_basis="Working capital at a concessional rate rather than a cash transfer",
        source_note="Limits and rates are set by the lending bank and revised periodically.",
    ),
    Scheme(
        key="soil_health_card",
        name="Soil Health Card",
        authority="Department of Agriculture & Farmers Welfare",
        beneficiary="FARMER",
        portal_url="https://soilhealth.dac.gov.in/",
        summary=(
            "Free soil testing with a nutrient-status card and crop-wise fertiliser "
            "recommendations for the holding."
        ),
        criteria=(Criterion("is_landholder", "eq", True, "Holds cultivable land"),),
        documents=("Land record", "Identity proof"),
        benefit_basis=(
            "Avoided over-application of fertiliser; the value is the input spending it saves, "
            "not a transfer"
        ),
        source_note="Value is indirect and is not estimated here.",
    ),
    Scheme(
        key="fpo_formation_10k",
        name="Formation & Promotion of 10,000 FPOs",
        authority="Ministry of Agriculture & Farmers Welfare / SFAC / NABARD",
        beneficiary="ORGANIZATION",
        portal_url="https://sfacindia.com/FPOS.aspx",
        summary=(
            "Financial assistance to a producer organisation for management cost over the "
            "first years, plus an equity grant matched to member equity and a credit "
            "guarantee facility."
        ),
        criteria=(
            Criterion(
                "organization_type", "in", ("FPO", "FPC"), "Registered producer company or society"
            ),
            Criterion("member_count", "gte", 300, "Minimum membership (plains norm)"),
            Criterion("is_registered", "eq", True, "Registered and compliant"),
        ),
        documents=(
            "Certificate of incorporation",
            "Member register",
            "Audited accounts",
            "Business plan",
        ),
        benefit_basis="Management cost support and matching equity grant",
        source_note=(
            "Membership norms differ between plains and hill/NE districts and the grant "
            "structure has been revised; treat the threshold as indicative."
        ),
    ),
    Scheme(
        key="aif",
        name="Agriculture Infrastructure Fund",
        authority="Ministry of Agriculture & Farmers Welfare",
        beneficiary="ORGANIZATION",
        portal_url="https://agriinfra.dac.gov.in/",
        summary=(
            "Medium-to-long term debt for post-harvest infrastructure — warehouses, cold "
            "stores, grading and sorting units — with an interest subvention and credit "
            "guarantee."
        ),
        criteria=(
            Criterion(
                "organization_type", "in", ("FPO", "FPC", "PACS", "COOPERATIVE"), "Eligible entity"
            ),
            Criterion("has_business_plan", "eq", True, "Project report for the asset"),
        ),
        documents=("Detailed project report", "Registration", "Audited accounts", "Land document"),
        benefit_basis="Interest subvention on eligible project debt",
        source_note="Subvention rate and ceiling are set in the operational guidelines.",
    ),
    Scheme(
        key="smam",
        name="Sub-Mission on Agricultural Mechanization",
        authority="Department of Agriculture & Farmers Welfare",
        beneficiary="ORGANIZATION",
        portal_url="https://agrimachinery.nic.in/",
        summary=(
            "Subsidy on farm machinery and on establishing a Custom Hiring Centre, so small "
            "holdings get machine access without each buying a machine."
        ),
        criteria=(
            Criterion(
                "organization_type",
                "in",
                ("FPO", "FPC", "PACS", "SHG", "COOPERATIVE"),
                "Eligible entity",
            ),
            Criterion("is_registered", "eq", True, "Registered entity"),
        ),
        documents=("Registration", "Quotation for machinery", "Bank account", "Land or shed proof"),
        benefit_basis="Capital subsidy on eligible machinery, higher for a Custom Hiring Centre",
        source_note="Subsidy rates vary by machine, category and state.",
    ),
    Scheme(
        key="pmksy_micro",
        name="PMKSY — Per Drop More Crop (micro-irrigation)",
        authority="Department of Agriculture & Farmers Welfare",
        beneficiary="FARMER",
        portal_url="https://pmksy.gov.in/",
        summary=(
            "Subsidy on drip and sprinkler systems, at a higher rate for small and "
            "marginal holdings."
        ),
        criteria=(
            Criterion("is_landholder", "eq", True, "Holds cultivable land"),
            Criterion("has_water_source", "eq", True, "An assured water source to pressurise"),
        ),
        documents=("Land record", "Water source proof", "Quotation from an empanelled supplier"),
        benefit_basis="Capital subsidy on the system cost, rate depending on holding class",
        source_note="Rates are set by state and revised; holding-class differential is real.",
    ),
)


# --------------------------------------------------------------------------- inputs


@dataclass(frozen=True)
class FarmerFacts:
    """Facts we hold about one farmer. ``None`` means unknown, never false.

    The distinction is load-bearing: treating an unrecorded Aadhaar as "no Aadhaar" would
    mark thousands of eligible farmers ineligible and nobody would ever find out why.
    """

    farmer_id: uuid.UUID
    name: str
    facts: dict[str, Any]
    evidence: list[EvidenceRef] = field(default_factory=list)
    #: Purposes this farmer has consented to. Sensitive criteria are skipped without consent.
    consented_purposes: frozenset[str] = frozenset()


@dataclass(frozen=True)
class OrganizationFacts:
    organization_id: uuid.UUID
    name: str
    facts: dict[str, Any]
    evidence: list[EvidenceRef] = field(default_factory=list)


@dataclass(frozen=True)
class Assessment:
    """One farmer or organization against one scheme."""

    scheme_key: str
    scheme_name: str
    subject_type: str
    subject_id: uuid.UUID
    status: str  # ELIGIBLE | LIKELY_ELIGIBLE | INSUFFICIENT_DATA | NOT_ELIGIBLE
    met: list[str]
    failed: list[str]
    unknown: list[str]
    missing_documents: list[str]
    estimated_benefit_paise: int | None
    confidence: float
    rules_verified: bool
    evidence: list[EvidenceRef]
    deadline: dt.date | None = None


# --------------------------------------------------------------------------- computation


def _test(criterion: Criterion, facts: dict[str, Any]) -> bool | None:
    """True / False / None, where None means *we do not hold this fact*."""
    if criterion.attribute not in facts:
        return None
    actual = facts[criterion.attribute]
    if actual is None:
        return None
    match criterion.operator:
        case "exists":
            return True
        case "eq":
            return bool(actual == criterion.value)
        case "lte":
            return bool(actual <= criterion.value)
        case "gte":
            return bool(actual >= criterion.value)
        case "in":
            return actual in criterion.value
    return None


def assess(
    scheme: Scheme,
    subject_type: str,
    subject_id: uuid.UUID,
    name: str,
    facts: dict[str, Any],
    evidence: list[EvidenceRef],
    as_of: dt.date,
    consented_purposes: frozenset[str] = frozenset(),
    documents_held: frozenset[str] = frozenset(),
) -> Assessment:
    """Assess one subject against one scheme.

    Note what happens with a sensitive criterion and no consent: it is neither passed nor
    failed, it is left unknown and the assessment degrades to ``INSUFFICIENT_DATA``. Reading
    a consent-gated attribute to decide eligibility the farmer never asked us to check would
    be exactly the misuse FR-566 exists to prevent (INV-9).
    """
    met: list[str] = []
    failed: list[str] = []
    unknown: list[str] = []

    for criterion in scheme.criteria:
        if criterion.sensitive and "SERVICE_DELIVERY" not in consented_purposes:
            unknown.append(f"{criterion.description} (consent not given for this check)")
            continue
        result = _test(criterion, facts)
        if result is True:
            met.append(criterion.description)
        elif result is False:
            failed.append(criterion.description)
        else:
            unknown.append(criterion.description)

    if failed:
        status = "NOT_ELIGIBLE"
    elif unknown:
        status = "INSUFFICIENT_DATA"
    else:
        status = "LIKELY_ELIGIBLE" if not scheme.rules_verified else "ELIGIBLE"

    confidence = 0.85 if status == "NOT_ELIGIBLE" else 0.75
    if unknown:
        confidence = max(0.30, confidence - 0.15 * len(unknown))
    if not scheme.rules_verified:
        confidence = min(confidence, UNVERIFIED_CONFIDENCE_CEILING)

    deadline = None
    if scheme.window_close:
        month, day = scheme.window_close
        deadline = dt.date(as_of.year, month, day)
        if deadline < as_of:
            deadline = dt.date(as_of.year + 1, month, day)

    benefit = (
        scheme.benefit_low_paise
        if status in ("ELIGIBLE", "LIKELY_ELIGIBLE") and scheme.benefit_low_paise
        else None
    )

    return Assessment(
        scheme_key=scheme.key,
        scheme_name=scheme.name,
        subject_type=subject_type,
        subject_id=subject_id,
        status=status,
        met=met,
        failed=failed,
        unknown=unknown,
        missing_documents=[d for d in scheme.documents if d not in documents_held],
        estimated_benefit_paise=benefit,
        confidence=round(confidence, 3),
        rules_verified=scheme.rules_verified,
        evidence=evidence,
        deadline=deadline,
    )


def gap_summary(assessments: list[Assessment]) -> dict[str, list[str]]:
    """The single missing fact blocking the most farmers.

    The most useful output this module produces, and it falls out of counting rather than
    reasoning: if 812 assessments are blocked on the same unrecorded fact, one field-officer
    campaign unlocks all of them, and that beats 812 individual follow-ups.
    """
    blockers: dict[str, list[str]] = {}
    for assessment in assessments:
        for gap in assessment.unknown:
            blockers.setdefault(gap, []).append(str(assessment.subject_id))
    return dict(sorted(blockers.items(), key=lambda kv: -len(kv[1])))


# --------------------------------------------------------------------------- module entry


def run(inputs: ModuleInput) -> ModuleOutput:
    data = inputs.data
    farmers: list[FarmerFacts] = data.get("farmers") or []
    organization: OrganizationFacts | None = data.get("organization")
    as_of = inputs.as_of.date()
    documents_held: frozenset[str] = data.get("documents_held") or frozenset()

    findings: list[Finding] = []
    actions: list[ProposedAction] = []
    degraded: list[str] = [
        "Scheme eligibility rules are simplified and unverified against operational "
        f"guidelines (seed/sources.md S1-S12); confidence is capped at "
        f"{UNVERIFIED_CONFIDENCE_CEILING} and no assessment is treated as final."
    ]

    if not farmers and organization is None:
        return ModuleOutput(
            module=MODULE, version=VERSION, degraded_inputs=[*degraded, "no subjects to assess"]
        )

    farmer_assessments: list[Assessment] = []
    for scheme in SCHEMES:
        if scheme.beneficiary != "FARMER":
            continue
        for farmer in farmers:
            if not farmer.evidence:
                continue
            farmer_assessments.append(
                assess(
                    scheme,
                    "farmer",
                    farmer.farmer_id,
                    farmer.name,
                    farmer.facts,
                    farmer.evidence,
                    as_of,
                    farmer.consented_purposes,
                )
            )

    by_scheme: dict[str, list[Assessment]] = {}
    for assessment in farmer_assessments:
        by_scheme.setdefault(assessment.scheme_key, []).append(assessment)

    for scheme_key, group in by_scheme.items():
        scheme = next(s for s in SCHEMES if s.key == scheme_key)
        eligible = [a for a in group if a.status in ("ELIGIBLE", "LIKELY_ELIGIBLE")]
        blocked = [a for a in group if a.status == "INSUFFICIENT_DATA"]
        if not eligible and not blocked:
            continue
        value = sum(a.estimated_benefit_paise or 0 for a in eligible)
        evidence = [e for a in group[:3] for e in a.evidence[:1]]
        if not evidence:
            continue

        deadline_note = ""
        if group[0].deadline:
            days = (group[0].deadline - as_of).days
            deadline_note = (
                f" The window closes around {group[0].deadline:%d %b}"
                f"{' — under ' + str(days) + ' days away' if days <= URGENT_DAYS else ''}."
            )

        findings.append(
            Finding(
                key=f"scheme_eligibility.{scheme.key}",
                statement=(
                    f"{scheme.name}: {len(eligible)} members look eligible"
                    + (
                        f" and {len(blocked)} cannot be assessed for want of a recorded fact"
                        if blocked
                        else ""
                    )
                    + (
                        f", worth about Rs {format_lakh(value)} lakh a year in total"
                        if value
                        else ""
                    )
                    + f".{deadline_note}"
                ),
                magnitude=Decimal(value) if value else Decimal(len(eligible)),
                unit="paise" if value else "members",
                confidence=min(a.confidence for a in group),
                evidence=evidence,
                assumptions=[
                    "Rules are simplified — state amendments and district discretion are not "
                    "encoded. Treat this as a shortlist to check, not a determination.",
                    "Eligibility is assessed only on facts on record; nothing is inferred.",
                ],
                affected=AffectedSet(
                    farmer_ids=[a.subject_id for a in eligible],
                    value_paise=value or None,
                ),
            )
        )

        if eligible:
            actions.append(
                ProposedAction(
                    key=f"scheme_pursuit.{scheme.key}",
                    title=f"Prepare {scheme.name} applications for {len(eligible)} members",
                    rationale=(
                        f"{scheme.summary} These members meet every criterion we can check. "
                        f"The FPO can assemble the paperwork; each farmer files their own "
                        f"application at {scheme.portal_url} — this system never submits a "
                        f"government application on anyone's behalf (FR-567)."
                    ),
                    recommendation_type="SCHEME_PURSUIT",
                    target_type="scheme",
                    target_id=None,
                    value_paise=value or None,
                    value_unit="paise_per_year" if value else None,
                    expected_impact={
                        "metric": "member income from entitlements claimed",
                        "members": len(eligible),
                        "benefit_basis": scheme.benefit_basis,
                        "portal": scheme.portal_url,
                        "authority": scheme.authority,
                        "documents_required": list(scheme.documents),
                        "auto_submit": False,
                        "rules_verified": scheme.rules_verified,
                        "caveat": scheme.source_note,
                    },
                    risks=[
                        "Simplified rules: some of these members will turn out ineligible on "
                        "a criterion we do not hold.",
                        "Deadlines are notified per state and are not encoded here.",
                    ],
                    alternatives=[
                        "Run a document camp first and file once, rather than filing and "
                        "being rejected for a missing paper."
                    ],
                    confidence=min(a.confidence for a in eligible),
                    evidence=evidence,
                )
            )

    gaps = gap_summary(farmer_assessments)
    for gap, subjects in list(gaps.items())[:3]:
        sample = [a for a in farmer_assessments if str(a.subject_id) in subjects[:3]]
        evidence = [e for a in sample for e in a.evidence[:1]]
        if not evidence:
            continue
        findings.append(
            Finding(
                key=f"scheme_gap.{gap[:40].lower().replace(' ', '_')}",
                statement=(
                    f"One unrecorded fact — {gap.lower()} — blocks {len(set(subjects))} "
                    f"eligibility assessments. A single field campaign clears all of them."
                ),
                magnitude=Decimal(len(set(subjects))),
                unit="assessments blocked",
                confidence=0.80,  # a count of our own gaps, not a claim about the world
                evidence=evidence,
                assumptions=["Counts assessments, not farmers — one farmer may appear twice."],
                affected=AffectedSet(farmer_ids=[uuid.UUID(s) for s in set(subjects)]),
            )
        )

    if organization is not None and organization.evidence:
        for scheme in SCHEMES:
            if scheme.beneficiary != "ORGANIZATION":
                continue
            assessment = assess(
                scheme,
                "organization",
                organization.organization_id,
                organization.name,
                organization.facts,
                organization.evidence,
                as_of,
                frozenset({"SERVICE_DELIVERY"}),
                documents_held,
            )
            if assessment.status == "NOT_ELIGIBLE":
                continue
            status_text = assessment.status.lower().replace("_", " ")
            missing = (
                f" Missing: {', '.join(assessment.missing_documents)}."
                if assessment.missing_documents
                else ""
            )
            unresolved = (
                f" Cannot yet check: {', '.join(assessment.unknown)}." if assessment.unknown else ""
            )
            findings.append(
                Finding(
                    key=f"org_scheme.{scheme.key}",
                    statement=(
                        f"{scheme.name}: the organization is {status_text}.{unresolved}{missing}"
                    ),
                    confidence=assessment.confidence,
                    evidence=assessment.evidence,
                    assumptions=[scheme.source_note or "Rules simplified and unverified."],
                    affected=AffectedSet(),
                )
            )
            if assessment.status in ("ELIGIBLE", "LIKELY_ELIGIBLE"):
                actions.append(
                    ProposedAction(
                        key=f"org_scheme_pursuit.{scheme.key}",
                        title=f"Pursue {scheme.name}",
                        rationale=(
                            f"{scheme.summary} The organization meets the criteria on record. "
                            f"Apply at {scheme.portal_url}. Nothing is submitted automatically."
                        ),
                        recommendation_type="SCHEME_PURSUIT",
                        target_type="organization",
                        target_id=organization.organization_id,
                        value_paise=assessment.estimated_benefit_paise,
                        value_unit="paise" if assessment.estimated_benefit_paise else None,
                        expected_impact={
                            "metric": "organization capital access",
                            "benefit_basis": scheme.benefit_basis,
                            "portal": scheme.portal_url,
                            "authority": scheme.authority,
                            "documents_required": list(scheme.documents),
                            "documents_missing": assessment.missing_documents,
                            "auto_submit": False,
                            "rules_verified": scheme.rules_verified,
                        },
                        risks=[
                            "Rules encoded here are simplified; confirm against the current "
                            "operational guidelines before spending time on the application.",
                        ],
                        alternatives=[],
                        confidence=assessment.confidence,
                        evidence=assessment.evidence,
                    )
                )

    return ModuleOutput(
        module=MODULE,
        version=VERSION,
        findings=findings,
        proposed_actions=actions,
        degraded_inputs=degraded,
    )
