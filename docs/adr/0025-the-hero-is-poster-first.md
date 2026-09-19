# ADR-0025 — The landing hero is three clips, poster-first

Date: 2026-09-19 · Status: Accepted

## Context

Five stock clips were supplied for the landing page: 68 MB of 1080p60 and 4K footage. Two
of them are 768×432 comp previews carrying a burned-in *iStock by Getty Images* watermark
across the centre of the frame.

A hero that ships 68 MB is a hero that loses the visitor before it loads, and a video hero
is the classic Largest Contentful Paint regression. The page is also the one a demo is given
from, sometimes on venue wifi, sometimes on none.

## Decision

- **Three slides, not five.** The hero carries the three clean HD clips. The watermarked
  pair plays in `FieldStrip` lower down the page, at their native 768×432, where neither
  the softness nor the mark is magnified.
- **Poster-first.** Every slide always renders a committed `next/image` poster. Video is an
  upgrade applied after mount, and only when the viewport is ≥768px, Save-Data is off, the
  connection is not 2G/3G, `prefers-reduced-motion` is unset, and a CDN is configured. The
  initial render — server and first client paint alike — contains no `<video>` at all.
- **Posters are committed; videos are not.** `apps/web/public/hero/*.jpg` (~660 KB total)
  ships with the app. The five `.mp4` files (~3.8 MB) live in blob storage behind
  `NEXT_PUBLIC_VIDEO_BASE_URL`. **Leaving that variable unset is a supported mode**, not a
  misconfiguration: the hero runs as a poster slideshow, which is what keeps
  `make seed && make dev` reproducing the demo with no network.
- **H.264 only, no WebM.** A VP9 sibling was built and measured: on this grainy,
  downscaled-4K footage it came out roughly twice the size of x264 at matched quality.
  H.264 plays everywhere, so the second rendition cost storage and transcode time and
  bought nothing.
- **Budgets are asserted.** `scripts/build_hero_media.py` fails the run when a rendition
  exceeds its ceiling (1.5 MB hero, 500 KB strip, 300 KB poster). The first run breached
  every hero budget at CRF 23; 1280-wide at CRF 32 is what actually fits.
- **An Animation Tier 1 exception, named and bounded.** `--motion-slide: 700ms` on
  `transform` only, with the house `cubic-bezier(0, 0, 0.2, 1)`, zeroed under
  reduced-motion. Nothing else may use the token.

## Consequences

**Easier.** The LCP element is an optimized image, not a video. A phone never downloads a
megabyte of footage. Only the current slide and the next one own a `<video>` element, so a
visitor who leaves after eight seconds paid for one clip. The demo cannot be killed by the
network.

**Harder.** The carousel is hand-written — autoplay, pause, indicators, `inert` on
off-screen slides, reduced-motion, keyboard. That is about 200 lines that a library would
have provided, and it is covered by tests for exactly that reason.

**Accepted, and this one has consequences outside the repo.** Clips 4 and 5 ship with their
watermarks visible. This was raised three times and confirmed as a deliberate choice. They
are unlicensed comp previews: the mark is centred and survives every usable crop — measured,
not assumed — so it cannot be framed out, and cropping it out would be licence laundering
rather than a fix. Publishing them to a production domain is a licensing exposure, and they
will read as unfinished to a funder. **The swap path is two lines in
`components/landing/content.ts`**: replacing the two files needs no code change. Until then,
prefer not to deploy the strip to a public domain.

**Rejected.** A carousel library (40 KB, and the app's runtime dependencies are exactly
three). A single looping clip (one clip cannot carry three messages). Cropping the
watermark (see above). The `poster` attribute on `<video>` rather than an image layer —
the layer gives one optimized AVIF/WebP fetch instead of a second raw JPEG, and it *is* the
no-network mode.
