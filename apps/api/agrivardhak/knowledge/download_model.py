"""``make embed-model`` — fetch the ONNX sentence encoder once, into a local cache.

Deliberately a separate, explicit step rather than a lazy download on first use. The demo
must run with the network unplugged and there is a test that blocks sockets to prove it
(NFR-303); a library that quietly fetched weights the first time it was called would pass
every local run and fail on the day.

The model is ``paraphrase-multilingual-MiniLM-L12-v2`` exported to ONNX. Multilingual
matters — the corpus is Hindi, and an English-only encoder would place
``लघु एवं सीमांत कृषक`` nowhere near ``small and marginal farmer``.

Nothing else in the system imports this module. If it is never run, ``embed.available()``
stays false and retrieval uses Postgres full-text search instead.
"""

from __future__ import annotations

import argparse
import pathlib
import platform
import sys
import urllib.request

from agrivardhak.knowledge.embed import DIM, model_dir

REPO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
BASE = f"https://huggingface.co/{REPO}/resolve/main"

#: The int8 exports are 118 MB against 470 MB for float32, but they are built per CPU
#: architecture and an AVX-512 graph will not load on arm64. Chosen by machine, with the
#: portable float32 build as the last resort rather than a failed download.
QUANTISED_BY_MACHINE = {
    "arm64": "onnx/model_qint8_arm64.onnx",
    "aarch64": "onnx/model_qint8_arm64.onnx",
    # AVX2 rather than AVX-512: near-universal on x86_64 since 2013, where AVX-512 is not.
    "x86_64": "onnx/model_quint8_avx2.onnx",
    "amd64": "onnx/model_quint8_avx2.onnx",
}
FLOAT32_FALLBACK = "onnx/model.onnx"


def _model_remote() -> str:
    machine = platform.machine().lower()
    return QUANTISED_BY_MACHINE.get(machine, FLOAT32_FALLBACK)


def download(destination: pathlib.Path | None = None, *, force: bool = False) -> int:
    target = destination or model_dir()
    target.mkdir(parents=True, exist_ok=True)
    files = ((_model_remote(), "model.onnx"), ("tokenizer.json", "tokenizer.json"))
    print(f"  architecture      {platform.machine()} -> {files[0][0]}")
    for remote, local in files:
        path = target / local
        if path.is_file() and not force:
            print(f"  {local}: already present")
            continue
        url = f"{BASE}/{remote}"
        print(f"  {local}: downloading from {url}")
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                path.write_bytes(response.read())
        except Exception as exc:
            print(f"\n  failed: {exc}", file=sys.stderr)
            print(
                "  Retrieval still works without the encoder — it falls back to Postgres "
                "full-text search. Re-run this when the network allows.",
                file=sys.stderr,
            )
            return 1
    print(f"\nEncoder ready in {target} ({DIM}-d vectors).")
    print("Re-run `make ingest` to backfill embeddings for chunks already stored.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    args = parser.parse_args()
    return download(force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
