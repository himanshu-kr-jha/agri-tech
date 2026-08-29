"""Confidence ceilings on retrieved knowledge (ADR-0014, ADR-0012).

Nine of the ten sources in ``seed/source_registry.py`` carry ``licence = "UNKNOWN"``, and the
one that does not is cleared for non-commercial use only. ADR-0014 is explicit about what
that means: *"A confidence cap lifts only when a human sets ``verified_by``, and the
corresponding ``seed/sources.md`` row exists and carries a licence."*

So the question this module answers is not "how good is this text?" but "may this text
influence advice yet?". The answer is enforced the way the repository already enforces it
elsewhere — with a ceiling placed deliberately below the orchestrator's confidence floor, so
that unusable knowledge is *structurally* unable to reach a recommendation rather than
merely discouraged from doing so. ``intelligence/crop_health.py`` does the same thing at
0.42, and the comment there applies verbatim: the cap is doing useful work.

The consequence to expect on day one: nothing is verified, so nothing lifts. Scheme
behaviour is unchanged until a human reviews the extractions. That is the design working.
"""

from __future__ import annotations

from agrivardhak.domain.enums import VerificationStatus

#: The orchestrator's default ``confidence_floor`` in ``engine.ask``. Mirrored here so the
#: relationship between the two numbers is visible at the point the ceiling is chosen; the
#: test asserts against ``engine.ask`` rather than against this constant.
ORCHESTRATOR_FLOOR = 0.45

#: Licence unknown, or known and not cleared for our use. Below the floor by construction:
#: such a chunk may be shown as context, and may never drive a recommendation.
INERT_LICENCE_CEILING = 0.40

#: Licence is fine, but the structured fields were proposed by a model and no human has
#: confirmed the transcription. Matches ``scheme.UNVERIFIED_CONFIDENCE_CEILING`` — the same
#: claim, reached the same way.
UNVERIFIED_EXTRACTION_CEILING = 0.55

#: A source whose licence field still says this has not been cleared by anyone.
UNKNOWN_LICENCE = "UNKNOWN"

#: Substrings that mark a licence as recorded but not cleared for product use. Checked
#: case-insensitively. Kept as a list because the wording differs per publisher and guessing
#: a canonical form would be the same mistake as guessing the licence.
NOT_CLEARED_MARKERS = ("COMMERCIAL USE NOT CLEARED", "NON-COMMERCIAL")


def licence_is_usable(licence: str | None, *, commercial: bool) -> bool:
    """Whether a source's licence permits the use we are actually making of it.

    ``commercial`` is the caller's honest description of the deployment. AgriVardhak is
    built as a public-good entry, so the demo path passes ``False`` — but the flag exists so
    that the day someone asks "can we sell this?", the answer is computed from the recorded
    licences rather than remembered.
    """
    if not licence or licence.strip().upper() == UNKNOWN_LICENCE:
        return False
    if not commercial:
        return True
    upper = licence.upper()
    return not any(marker in upper for marker in NOT_CLEARED_MARKERS)


def ceiling_for(
    *,
    licence: str | None,
    verification_status: VerificationStatus,
    has_extraction: bool = False,
    commercial: bool = False,
) -> float:
    """The highest confidence a claim resting on this chunk may carry.

    Returns 1.0 when nothing constrains it — the caller still applies source trust and age
    decay on top, so 1.0 means "no *gate* applies", not "certain".
    """
    if not licence_is_usable(licence, commercial=commercial):
        return INERT_LICENCE_CEILING
    if verification_status is VerificationStatus.VERIFIED:
        return 1.0
    if has_extraction:
        return UNVERIFIED_EXTRACTION_CEILING
    return 1.0


def may_lift_a_cap(
    *, licence: str | None, verification_status: VerificationStatus, commercial: bool = False
) -> bool:
    """ADR-0014's gate, in one place.

    Both halves are required: a named human *and* a licence on record. A fetch cannot assert
    that a transcription faithfully represents the published text, and a faithful
    transcription of text we have no right to use is still not usable.
    """
    return verification_status is VerificationStatus.VERIFIED and licence_is_usable(
        licence, commercial=commercial
    )
