"""The local sentence encoder — optional, and off the critical path (DR-07, NFR-303).

``paraphrase-multilingual-MiniLM-L12-v2`` exported to int8 ONNX, run through
``onnxruntime``. The multilingual variant matters: the corpus is Hindi, and an
English-only encoder would put ``लघु एवं सीमांत कृषक`` and ``small and marginal farmer``
in unrelated regions of the space.

Two constraints shaped this over the obvious ``sentence-transformers`` choice.

**The demo runs with the network unplugged (NFR-303), and there is a test that blocks
sockets to prove it.** A library that lazily downloads weights on first call fails that test
in a way that only shows up at demo time. So the model is fetched once by ``make
embed-model`` into a directory on disk, and this module never reaches for the network.

**Absence is a supported state, not an error.** ``available()`` is false before
``make embed-model`` runs, on a fresh clone, and in CI. Retrieval then falls back to Postgres
full-text search rather than failing — the same shape as ``orchestrator/llm.py`` degrading to
a keyword router and ``narrator.py`` returning the packet unchanged when no model is
configured. A weaker answer beats no answer.
"""

from __future__ import annotations

import functools
import logging
import math
import os
import pathlib
from typing import Any

log = logging.getLogger(__name__)

#: 384 for MiniLM-L12. Must equal ``domain.models.knowledge.EMBEDDING_DIM``; a mismatch is a
#: migration, not a setting, because every stored vector would otherwise be meaningless.
DIM = 384

#: Longest input the model was trained on. Longer text is truncated rather than rejected —
#: ``segment.py`` should already have kept passages well under this.
MAX_TOKENS = 128

DEFAULT_MODEL_DIR = pathlib.Path(__file__).resolve().parents[2] / "models" / "multilingual-minilm"


def model_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("AGRI_EMBED_MODEL_DIR") or DEFAULT_MODEL_DIR)


@functools.lru_cache(maxsize=1)
def _session() -> tuple[Any, Any] | None:
    """Load the ONNX session and tokenizer, or return None if either is unavailable.

    Cached because loading costs ~200 ms and the observer calls this per batch. Every failure
    path is a warning and a None, never a raise: a missing encoder must degrade retrieval,
    not break ingestion.
    """
    directory = model_dir()
    onnx_path = directory / "model.onnx"
    tokenizer_path = directory / "tokenizer.json"
    if not onnx_path.is_file() or not tokenizer_path.is_file():
        log.info("no sentence encoder at %s — retrieval will use lexical search only", directory)
        return None
    try:
        import onnxruntime
        from tokenizers import Tokenizer
    except ImportError:
        log.warning("onnxruntime/tokenizers not installed — retrieval will use lexical search")
        return None
    try:
        tokenizer = Tokenizer.from_file(str(tokenizer_path))
        tokenizer.enable_truncation(max_length=MAX_TOKENS)
        tokenizer.enable_padding()
        session = onnxruntime.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    except Exception as exc:  # pragma: no cover - corrupt download
        log.warning("sentence encoder at %s failed to load: %s", directory, exc)
        return None
    return session, tokenizer


def available() -> bool:
    """Whether dense retrieval is possible right now."""
    return _session() is not None


def encode(texts: list[str]) -> list[list[float]] | None:
    """Embed passages as unit-length 384-d vectors, or return None if no encoder is present.

    Mean-pools the token states over the attention mask — the pooling
    ``sentence-transformers`` applies for this checkpoint — then L2-normalises, so cosine
    similarity is a dot product and pgvector's ``vector_cosine_ops`` behaves as expected.
    """
    if not texts:
        return []
    loaded = _session()
    if loaded is None:
        return None
    session, tokenizer = loaded

    import numpy as np

    encodings = tokenizer.encode_batch(texts)
    ids = np.array([e.ids for e in encodings], dtype=np.int64)
    mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)

    feed = {"input_ids": ids, "attention_mask": mask}
    expected = {i.name for i in session.get_inputs()}
    if "token_type_ids" in expected:
        feed["token_type_ids"] = np.zeros_like(ids)
    feed = {k: v for k, v in feed.items() if k in expected}

    hidden = session.run(None, feed)[0]  # (batch, tokens, dim)
    weights = mask[..., None].astype(hidden.dtype)
    pooled = (hidden * weights).sum(axis=1) / np.clip(weights.sum(axis=1), 1e-9, None)
    norms = np.linalg.norm(pooled, axis=1, keepdims=True)
    pooled = pooled / np.clip(norms, 1e-9, None)
    return [[float(x) for x in row] for row in pooled]


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity for already-normalised vectors, defensive about the general case.

    Used by ``segment.py`` to find topic breakpoints, where the vectors come straight from
    :func:`encode` and are unit-length; the norm division is kept so that a caller passing
    raw vectors still gets a correct answer rather than a confident wrong one.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)
