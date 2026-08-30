"""Splitting a document into retrievable passages.

Semantic chunking, with an honest short-circuit.

The method is the standard one: split into sentences, embed each, and start a new chunk
where the similarity between consecutive sentences drops below a breakpoint — so a passage
breaks where the *topic* changes rather than where a character budget runs out. That matters
for the agridarshan FAQ answers, which run several hundred words across distinct sub-topics,
and it will matter more when the government-order PDFs are fetched.

**It matters very little for the corpus as it stands, and the code says so out loud.**
The शासनादेश scraper harvests listing rows, not documents: the ``subject`` field averages
199 characters and tops out at 329. Chunking a single Hindi sentence into "semantic" pieces
would fragment one statement into several worse ones and multiply the citation count without
adding a single retrievable fact. So a document shorter than ``min_chars`` returns as one
chunk, via an early return that exists to be read rather than discovered.

When no encoder is present (NFR-303, see ``embed.py``) the split falls back to packing whole
sentences up to ``max_chars``. Sentence boundaries are respected either way; the difference
is only whether the boundary is chosen by meaning or by length.
"""

from __future__ import annotations

import html
import re

from agrivardhak.knowledge import embed

#: A document at or under this length is one chunk. Set above the longest government-order
#: subject in the corpus (329 characters) so the common case never splits.
DEFAULT_MIN_CHARS = 600

#: Hard ceiling on a chunk, comfortably inside the encoder's 128-token window for Devanagari.
DEFAULT_MAX_CHARS = 900

#: Cosine similarity below which consecutive sentences are treated as different topics.
#: 0.5 is deliberately permissive: over-merging costs a little retrieval precision, while
#: over-splitting costs whole statements, and a split statement cannot be cited coherently.
BREAKPOINT = 0.5

#: Devanagari danda and double danda end a sentence, as do the Latin terminators the
#: bilingual CMS text uses. The class also carries U+097D, DEVANAGARI LETTER GLOTTAL
#: STOP, which the agridarshan FAQ titles genuinely use as their question mark. Ruff
#: reads it as a typo for ASCII '?'; here it is the real published character, and
#: substituting one would stop the actual text from splitting. Hence the noqa below,
#: and hence the glyph is named rather than written in this comment.
_SENTENCE_END = re.compile(r"(?<=[।॥.!?ॽ])\s+|\n+")  # noqa: RUF001

_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"[ \t\r\f\v]+")


def strip_markup(text: str) -> str:
    """Remove the HTML the agridarshan CMS ships inside its JSON answer fields.

    The payload carries raw ``<p>`` and ``&nbsp;`` and there is no sanitiser anywhere in the
    fetch path. Tags are removed for indexing only — the raw payload keeps them, so the
    evidence trail still points at exactly what was published.
    """
    without_tags = _TAG.sub(" ", text)
    unescaped = html.unescape(without_tags)
    return _WHITESPACE.sub(" ", unescaped.replace("\xa0", " ")).strip()


def sentences(text: str) -> list[str]:
    """Split on sentence terminators, dropping empties."""
    return [part.strip() for part in _SENTENCE_END.split(text) if part.strip()]


def segment(
    text: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    min_chars: int = DEFAULT_MIN_CHARS,
    breakpoint: float = BREAKPOINT,
) -> list[str]:
    """Split ``text`` into retrievable passages. Always returns at least one chunk for
    non-empty input."""
    cleaned = strip_markup(text)
    if not cleaned:
        return []

    # The common case for this corpus: the whole document is already one passage.
    if len(cleaned) <= min_chars:
        return [cleaned]

    parts = sentences(cleaned)
    if len(parts) <= 1:
        return [cleaned] if len(cleaned) <= max_chars else _hard_wrap(cleaned, max_chars)

    vectors = embed.encode(parts)
    if vectors is None:
        return _pack(parts, max_chars)
    return _pack_semantic(parts, vectors, max_chars, breakpoint)


def _pack(parts: list[str], max_chars: int) -> list[str]:
    """Greedy length packing — the fallback when no encoder is available."""
    chunks: list[str] = []
    current = ""
    for part in parts:
        candidate = f"{current} {part}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = part
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _pack_semantic(
    parts: list[str], vectors: list[list[float]], max_chars: int, breakpoint: float
) -> list[str]:
    """Merge consecutive sentences while they stay on topic and inside the budget."""
    chunks: list[str] = []
    current = parts[0]
    for index in range(1, len(parts)):
        similarity = embed.cosine(vectors[index - 1], vectors[index])
        candidate = f"{current} {parts[index]}".strip()
        if similarity < breakpoint or len(candidate) > max_chars:
            chunks.append(current)
            current = parts[index]
        else:
            current = candidate
    chunks.append(current)
    return chunks


def _hard_wrap(text: str, max_chars: int) -> list[str]:
    """Last resort for a single sentence longer than the budget: split on whitespace.

    Reached only by pathological input — an unpunctuated wall of text. Splitting mid-word
    would corrupt Devanagari conjuncts, so word boundaries are respected even here.
    """
    words = text.split(" ")
    chunks: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks
