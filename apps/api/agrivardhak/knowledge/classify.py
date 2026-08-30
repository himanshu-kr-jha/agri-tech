"""Is this passage worth indexing, and what is it about? (FR-404)

Deterministic on purpose. A binary gate at ingestion volume is the wrong place for a model
call: it costs money per document, it is not replayable, and it would put a non-deterministic
step upstream of an ``EvidenceSnapshot`` that INV-2 requires to reproduce exactly. Government
orders are also strongly structured — the publisher already tells us the category — so the
signal a model would have to infer is sitting in a field.

**The Unicode trap this module exists to survive.** The scraped Hindi is stored verbatim
(ADR-0015), and the source page emits zero-width joiners inside conjuncts:
``'वित्‍तीय स्‍वीकृतियॉं'`` is what 52 of the 75 orders carry as their category.
A literal match against ``'वित्तीय स्वीकृतियॉं'`` — the same word, typed normally — silently
fails, and every financial sanction would be classified as unknown while looking fine. So
matching runs over a normalised copy; the stored text is never touched.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from agrivardhak.domain.enums import NewsDomain

#: Zero-width joiner and non-joiner. Invisible, and fatal to naive matching.
_ZERO_WIDTH = dict.fromkeys(map(ord, "‌‍﻿"))

#: Below this a passage cannot carry a scheme statement. The shortest real government-order
#: subject in the corpus is 66 characters; a CMS caption ("खेती") is four.
MIN_USEFUL_CHARS = 40


def normalise(text: str) -> str:
    """A matching key: NFC, zero-width characters removed, whitespace collapsed, lowercased.

    Never persisted. ``KnowledgeChunk.text_hi`` keeps the published bytes.
    """
    folded = unicodedata.normalize("NFC", text).translate(_ZERO_WIDTH)
    return re.sub(r"\s+", " ", folded).strip().lower()


@dataclass(frozen=True)
class Classification:
    is_noise: bool
    noise_reason: str | None
    news_domain: NewsDomain | None
    #: True when the passage is scheme guidance rather than an administrative act. Only
    #: these are worth proposing structured eligibility fields from.
    is_scheme_guidance: bool = False


# --------------------------------------------------------------------------- noise

#: Administrative acts about departmental staff. Real government orders, and nothing to do
#: with farming — 52 of the 69 agridarshan circulars are promotions and postings.
_PERSONNEL = (
    "पदोन्नति",
    "पद्दोंनती",
    "प्रोन्नति",  # promotion (the portal spells it three ways)
    "नियुक्ति",  # appointment
    "स्थानांतरण",
    "स्थानान्तरण",
    "तबादला",  # transfer
    "सेवानिवृत्त",
    "सेवानिवृत्ति",  # retirement
    "अवकाश",  # leave
    "भर्ती",
    "नवचयनित",
    "चयन आयोग",  # recruitment / selection board
    "वेतन आयोग",
    "भत्ते संबंधी",  # pay commission / allowances
    "कार्यालय ज्ञाप",  # office memorandum
    # The agridarshan CMS files staff seniority lists as "circulars". They were the single
    # largest source of noise reaching a reader — 39 domain-less chunks, most of them
    # ज्येष्ठता सूची, which a farmer-facing feed surfaced as departmental notices.
    # Unambiguous: no agricultural notice uses these words.
    "ज्येष्ठता",
    "जयेष्टता",
    "ज्येष्टत्ता",  # seniority — the portal spells it three ways
    "संवर्ग",  # service cadre
    "लिपिक",  # clerk
)

_PERSONNEL_CATEGORIES = ("वेतन/भत्ते संबंधी नीतिगत निर्णय",)

# --------------------------------------------------------------------------- domain

#: Publisher's own category → domain. The most reliable signal available, and free.
_CATEGORY_DOMAIN: tuple[tuple[str, NewsDomain, bool], ...] = (
    # (normalised category substring, domain, is_scheme_guidance)
    ("नीतियोँ/योजनाओं संबंधी दिशा-निर्देश", NewsDomain.POLICY, True),
    ("अधिसूचना", NewsDomain.POLICY, True),
    ("आयोजनागत वित्तीय स्वीकृति", NewsDomain.POLICY, False),
    ("वित्तीय स्वीकृति", NewsDomain.POLICY, False),
)

#: Subject keywords that refine the category into a more specific domain. First match wins,
#: so ordering is the whole design.
#:
#: Insurance leads deliberately. ``प्रधानमंत्री फसल बीमा योजना एवं पुनर्गठित मौसम आधारित फसल
#: बीमा योजना`` contains ``मौसम`` (weather) and would otherwise land in CLIMATE — but a crop
#: insurance notification is a policy instrument, not a weather event, and filing it under
#: CLIMATE would put it in front of a CEO asking about hazards rather than about schemes.
#:
#: There is no generic POLICY group. ``योजना`` and ``अनुदान`` appear in almost every order,
#: so matching on them would swallow the specific domains whole. POLICY is what the
#: publisher's category already means; keywords exist only to say "actually, more specific".
_KEYWORD_DOMAIN: tuple[tuple[tuple[str, ...], NewsDomain], ...] = (
    (("बीमा",), NewsDomain.POLICY),
    # Machinery is a farm input like any other, and the mechanisation programmes are among
    # the few notices with a direct, actionable bearing on a smallholder.
    (
        (
            "उर्वरक",
            "खाद",
            "बीज ",
            "बीज विकास",
            "कीटनाशक",
            "कृषि यंत्र",
            "कृषि यन्त्र",
            "यंत्रीकरण",
            "यन्त्रीकरण",
            "मैकेनाइजेशन",
        ),
        NewsDomain.INPUT_PRICE,
    ),
    (("भण्डारण", "भंडारण", "परिवहन", "गोदाम", "आपूर्ति श्रृंखला"), NewsDomain.SUPPLY_CHAIN),
    (("क्रय", "खरीद", "मंडी", "विपणन", "समर्थन मूल्य"), NewsDomain.MARKET),
    (("सूखा", "बाढ़", "अतिवृष्टि", "मौसम", "सिंचाई", "नलकूप", "जल संरक्षण"), NewsDomain.CLIMATE),
)


def classify(
    text: str,
    *,
    category: str | None = None,
    is_advisory: bool = False,
) -> Classification:
    """Decide whether a passage is indexable, and which risk domain it speaks to.

    ``category`` is the publisher's own label where there is one (the शासनादेश GridView has
    a category column). ``is_advisory`` marks an ADVISORY-tier source under ADR-0012 — FAQs
    and circulars are guidance, not text a rule may be transcribed from.
    """
    body = normalise(text)
    cat = normalise(category) if category else ""

    if len(body) < MIN_USEFUL_CHARS:
        return Classification(True, "too short to carry a statement", None)

    if any(marker in cat for marker in map(normalise, _PERSONNEL_CATEGORIES)):
        return Classification(True, "departmental pay and allowances, not agriculture", None)

    for marker in _PERSONNEL:
        if normalise(marker) in body:
            return Classification(True, f"personnel administration ({marker})", None)

    domain: NewsDomain | None = None
    guidance = False
    for needle, mapped, is_guidance in _CATEGORY_DOMAIN:
        if normalise(needle) in cat:
            domain, guidance = mapped, is_guidance
            break

    # A more specific reading of the subject overrides the category: a budget sanction
    # naming fertiliser is an input-cost signal, not a generic policy one.
    for needles, mapped in _KEYWORD_DOMAIN:
        if any(normalise(n) in body for n in needles):
            domain = mapped
            break

    if domain is None:
        # An advisory FAQ is useful context but is not a policy event; it gets indexed
        # without a domain so it never appears in the risk register.
        if is_advisory:
            return Classification(False, None, None)
        return Classification(True, "no recognisable policy or scheme content", None)

    return Classification(False, None, domain, is_scheme_guidance=guidance)
