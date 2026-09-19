#!/usr/bin/env python3
"""Transcode the landing-page footage into web renditions (ADR-0025).

The source clips are 68 MB of 1080p60 and 4K stock footage. Shipping them as-is would
make the one page a judge opens cold the slowest page in the product, so each clip is
trimmed to a single beat, stripped of audio, and encoded once as H.264, plus a poster JPEG.

Only H.264. A VP9/WebM sibling was measured and rejected: on this grainy, downscaled-4K
footage it came out roughly twice the size of x264 at matched quality, and H.264 plays
everywhere, so the second rendition bought nothing and cost storage, transcode time and a
two-`<source>` player.

The posters are the important output. They are committed to ``apps/web/public/hero/`` and
are what the hero renders when there is no network, no CDN, on a phone, on Save-Data, or
under ``prefers-reduced-motion``. The videos are an upgrade, uploaded separately to blob
storage; see ``--print-upload``.

Budgets are asserted, not hoped for: a rendition over budget fails the run. A performance
budget nobody enforces is a performance wish.

Usage::

    make hero-media src=~/Downloads/stockvideos
    python scripts/build_hero_media.py --src ~/Downloads/stockvideos --out out/hero-media
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
POSTER_DEST = REPO_ROOT / "apps" / "web" / "public" / "hero"

KIB = 1024
MIB = 1024 * KIB


@dataclass(frozen=True)
class Clip:
    """One source clip and the single beat we keep from it."""

    #: Output basename. Shared by the .mp4 and the .jpg, and referenced verbatim by
    #: apps/web/src/components/landing/content.ts — rename in both or neither.
    name: str
    source: str
    #: Seek, in seconds, into the source. Applied before -i for a fast keyframe seek.
    start: float
    #: Kept duration. Six to eight seconds is one beat: long enough to read, short
    #: enough that a visitor who leaves never paid for the rest.
    duration: float
    #: Output width. Never larger than the source — upscaling stock footage only makes
    #: a bigger file that looks exactly as soft. 1280 for the hero: the footage plays
    #: full-bleed but under a scrim with display type over it, where 720p is indistinguishable
    #: from 1080p and costs a third as many bytes.
    width: int
    #: Poster width, which can exceed the video's. The poster is the LCP element and the
    #: only thing mobile and offline visitors ever see, so it is worth the extra pixels;
    #: next/image resizes it down for everyone else.
    poster_width: int
    fps: int
    #: Constant-rate factor. Tuned per clip against the budget below.
    crf: int
    #: Byte ceiling for the video. The hero plays full-bleed and can afford more than the
    #: small two-up strip further down the page. These are measured ceilings, not wishes —
    #: the run fails when one is breached.
    budget: int
    note: str


CLIPS: tuple[Clip, ...] = (
    Clip(
        name="hero-01-paddy",
        source="14416222-hd_1920_1080_60fps.mp4",
        start=3.0,
        duration=7.0,
        width=1280,
        poster_width=1600,
        fps=30,
        crf=32,
        budget=1_500 * KIB,
        note="Drone rise over green paddy; farmer inspecting the crop, then the field mosaic.",
    ),
    Clip(
        name="hero-02-grading",
        source="17867755-hd_1920_1080_60fps.mp4",
        start=1.5,
        duration=7.0,
        width=1280,
        poster_width=1600,
        fps=30,
        crf=32,
        budget=1_500 * KIB,
        note="Grading green mangoes into crates. Source carries AAC — -an matters here.",
    ),
    Clip(
        name="hero-03-harvest",
        source="6780097-uhd_3840_2160_25fps.mp4",
        start=2.0,
        duration=7.0,
        width=1280,
        poster_width=1600,
        fps=25,
        crf=32,
        budget=1_500 * KIB,
        note=(
            "Combine in ripe paddy at golden hour. 4K source, downscaled, and the most "
            "expensive clip of the five — moving grain across the whole frame. It sets the "
            "CRF for all three."
        ),
    ),
    Clip(
        name="strip-01-advisory",
        source="istockphoto-1365398932-640_adpp_is.mp4",
        start=0.5,
        duration=6.0,
        width=768,
        poster_width=768,
        fps=24,
        crf=30,
        budget=500 * KIB,
        note=(
            "Farmer reading a smartphone in a mustard field. WATERMARKED comp footage, kept "
            "at native 768x432 and never cropped — cropping the mark out would be licence "
            "laundering, and it is centred anyway. See ADR-0025."
        ),
    ),
    Clip(
        name="strip-02-officer",
        source="istockphoto-1492945427-640_adpp_is.mp4",
        start=4.0,
        duration=7.0,
        width=768,
        poster_width=768,
        fps=25,
        crf=31,
        budget=500 * KIB,
        note="Farmer and advisor with a tablet in young wheat. WATERMARKED comp footage.",
    ),
)

POSTER_BUDGET = 300 * KIB
#: How far into the kept beat the poster frame is taken. Far enough past the cut to miss
#: any fade-in, early enough to be the frame the viewer actually sees first.
POSTER_OFFSET = 1.5


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(f"\n$ {' '.join(cmd)}\n{result.stderr}\n")
        raise SystemExit(f"ffmpeg failed for: {' '.join(cmd[:6])}…")


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def encode_h264(clip: Clip, src: Path, dest: Path) -> None:
    run(
        # fmt: off
        [
            "ffmpeg", "-v", "error", "-y",
            "-ss", str(clip.start), "-i", str(src), "-t", str(clip.duration),
            "-an",
            "-vf", f"scale={clip.width}:-2,format=yuv420p",
            "-r", str(clip.fps),
            "-c:v", "libx264", "-profile:v", "high", "-level", "4.0",
            "-crf", str(clip.crf), "-preset", "slow",
            # A keyframe every two seconds with scene detection off: the loop restarts
            # cleanly and seeking stays cheap.
            "-g", str(clip.fps * 2), "-sc_threshold", "0",
            # Without faststart the moov atom lands at the end of the file and the
            # browser buffers the whole clip before painting a single frame.
            "-movflags", "+faststart",
            str(dest),
        ]
        # fmt: on
    )


def extract_poster(clip: Clip, src: Path, dest: Path) -> None:
    run(
        # fmt: off
        [
            "ffmpeg", "-v", "error", "-y",
            "-ss", str(clip.start + POSTER_OFFSET), "-i", str(src),
            "-frames:v", "1",
            "-vf", f"scale={clip.poster_width}:-2",
            "-q:v", "5",
            str(dest),
        ]
        # fmt: on
    )


def human(size: int) -> str:
    return f"{size / MIB:.2f} MB" if size >= MIB else f"{size / KIB:.0f} KB"


def build(src_dir: Path, out_dir: Path, *, install_posters: bool) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    print(f"{'clip':<20} {'mp4':>10} {'poster':>10}  duration  budget")
    print("-" * 62)

    for clip in CLIPS:
        src = src_dir / clip.source
        if not src.exists():
            failures.append(f"{clip.name}: source missing — {src}")
            continue

        mp4 = out_dir / f"{clip.name}.mp4"
        poster = out_dir / f"{clip.name}.jpg"

        encode_h264(clip, src, mp4)
        extract_poster(clip, src, poster)

        actual = probe_duration(mp4)
        print(
            f"{clip.name:<20} {human(mp4.stat().st_size):>10} "
            f"{human(poster.stat().st_size):>10}  {actual:.2f}s"
            f"   {human(clip.budget)}"
        )

        for path, budget in ((mp4, clip.budget), (poster, POSTER_BUDGET)):
            if path.stat().st_size > budget:
                failures.append(
                    f"{path.name}: {human(path.stat().st_size)} exceeds "
                    f"{human(budget)} — raise the CRF or shorten the trim"
                )

        # `-ss` before `-i` snaps to the nearest keyframe, so the kept beat can drift.
        # A whole second of drift means the trim no longer starts where it was chosen to.
        if abs(actual - clip.duration) > 0.25:
            failures.append(
                f"{clip.name}: kept {actual:.2f}s, asked for {clip.duration:.2f}s "
                "— keyframe drift, adjust `start`"
            )

        if install_posters:
            POSTER_DEST.mkdir(parents=True, exist_ok=True)
            shutil.copy2(poster, POSTER_DEST / poster.name)

    return failures


def upload_hint(out_dir: Path) -> str:
    return (
        "\nUpload the videos (the posters are committed, the videos are not):\n\n"
        f"  npx vercel blob put {out_dir}/*.mp4 \\\n"
        '      --prefix hero --token "$BLOB_READ_WRITE_TOKEN"\n\n'
        "Then set, in apps/web/.env.local and in the Vercel project:\n\n"
        "  NEXT_PUBLIC_VIDEO_BASE_URL=https://<store-id>.public.blob.vercel-storage.com/hero\n\n"
        "Leaving it unset is a supported mode — the hero renders the committed posters.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--src",
        type=Path,
        default=Path.home() / "Downloads" / "stockvideos",
        help="Directory holding the source clips.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "out" / "hero-media",
        help="Where the renditions are written (gitignored).",
    )
    parser.add_argument(
        "--no-install-posters",
        action="store_true",
        help="Do not copy the posters into apps/web/public/hero/.",
    )
    args = parser.parse_args()

    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            sys.stderr.write(f"{tool} not found on PATH. `brew install ffmpeg`.\n")
            return 2

    src_dir = args.src.expanduser()
    if not src_dir.is_dir():
        sys.stderr.write(f"Source directory not found: {src_dir}\n")
        return 2

    failures = build(src_dir, args.out, install_posters=not args.no_install_posters)

    if failures:
        sys.stderr.write("\nFAILED:\n" + "\n".join(f"  - {f}" for f in failures) + "\n")
        return 1

    print(upload_hint(args.out))
    if not args.no_install_posters:
        print(f"Posters installed to {POSTER_DEST.relative_to(REPO_ROOT)}/ — commit them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
