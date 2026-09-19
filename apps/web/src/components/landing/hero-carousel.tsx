"use client";

/**
 * The hero — ADR-0025.
 *
 * Three clips of the work the product is about, each carrying one line. No carousel
 * library: this is a transform on a flex track and one timer, which is less code than the
 * adapter around a library would be, and it keeps the app's runtime dependencies at three.
 *
 * The shape that matters most here is **poster-first**. Every slide always renders its
 * still; video is an upgrade that happens after mount, only when the device and the
 * connection and the preference all say yes. That single decision buys four things at
 * once: the LCP element is an optimized image rather than a video, hydration cannot
 * mismatch (the server and the first client render agree — no video anywhere), phones and
 * Save-Data never download a megabyte of footage, and a laptop with no network still shows
 * a correct hero on stage.
 */

import Image from "next/image";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { posterSrc, videoSrc } from "@/lib/media";

export type Slide = { clip: string; eyebrow: string; headline: string };

export type HeroLabels = {
  carousel: string;
  pause: string;
  play: string;
  goToSlide: string;
};

/** Backstop when a clip stalls or when there is no video to end. */
const POSTER_DWELL_MS = 6000;
const VIDEO_CEILING_MS = 7500;

export function HeroCarousel({ slides, labels }: { slides: Slide[]; labels: HeroLabels }) {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const [suspended, setSuspended] = useState(false);
  // Poster-only until proven otherwise. This is also what the server renders, so the first
  // client render matches it and there is nothing to mismatch.
  const [withVideo, setWithVideo] = useState(false);
  const videos = useRef<(HTMLVideoElement | null)[]>([]);

  const count = slides.length;
  const advance = useCallback(() => setIndex((i) => (i + 1) % count), [count]);

  // Decide whether this visitor gets footage at all. In an effect, never during render:
  // matchMedia and navigator.connection do not exist on the server, and reading them in
  // render would make the first client paint disagree with the HTML.
  useEffect(() => {
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const wide = window.matchMedia("(min-width: 768px)");

    const decide = () => {
      const connection = (
        navigator as Navigator & {
          connection?: { saveData?: boolean; effectiveType?: string };
        }
      ).connection;
      const thin = /(^|-)(2g|3g)$/.test(connection?.effectiveType ?? "");
      const ok =
        !motion.matches &&
        wide.matches &&
        !connection?.saveData &&
        !thin &&
        videoSrc(slides[0]?.clip ?? "") !== null;
      setWithVideo(ok);
      // Someone who has asked for less motion gets a hero they step through themselves.
      if (motion.matches) setPaused(true);
    };

    decide();
    motion.addEventListener("change", decide);
    wide.addEventListener("change", decide);
    return () => {
      motion.removeEventListener("change", decide);
      wide.removeEventListener("change", decide);
    };
  }, [slides]);

  /**
   * Which slides own a `<video>` element: the current one and the one after it, and no
   * others. A visitor who leaves after eight seconds pays for one clip, not three.
   *
   * Derived rather than accumulated. Keeping a growing set of "everything visited" would
   * hold all three decoders alive for the rest of the session to save a re-fetch that the
   * HTTP cache already serves.
   */
  const carriesVideo = (i: number) =>
    withVideo && (i === index || i === (index + 1) % count);

  // Play the current clip, hold every other one. Autoplay can still be refused — an
  // unhandled rejection here would be an uncaught error in the console on every load.
  useEffect(() => {
    videos.current.forEach((video, i) => {
      if (!video) return;
      if (i === index && withVideo && !paused && !suspended) {
        video.muted = true;
        video.currentTime = 0;
        void video.play().catch(() => setWithVideo(false));
      } else {
        video.pause();
      }
    });
  }, [index, withVideo, paused, suspended]);

  // One timer, owned by one effect, rebuilt whenever anything it depends on changes.
  useEffect(() => {
    if (paused || suspended || count < 2) return;
    const ms = withVideo ? VIDEO_CEILING_MS : POSTER_DWELL_MS;
    const timer = window.setTimeout(advance, ms);
    return () => window.clearTimeout(timer);
  }, [index, paused, suspended, withVideo, count, advance]);

  // A backgrounded tab should not keep cycling a hero nobody is looking at.
  useEffect(() => {
    const onVisibility = () => setSuspended(document.hidden);
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  const step = (delta: number) => {
    setPaused(true); // An explicit move stops the rotation (W3C APG).
    setIndex((i) => (i + delta + count) % count);
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      step(1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      step(-1);
    }
  };

  const sources = useMemo(() => slides.map((s) => videoSrc(s.clip)), [slides]);

  return (
    <section
      role="region"
      aria-roledescription="carousel"
      aria-label={labels.carousel}
      onKeyDown={onKeyDown}
      // The full-bleed trick the Footer uses. `overflow-hidden` is not optional: without
      // it the off-screen slides extend the document and fight `body { overflow-x: clip }`.
      className="relative left-1/2 h-[min(84svh,720px)] w-screen -translate-x-1/2 overflow-hidden bg-sidebar"
      // Hover suspends the rotation without redrawing the control — a pause button that
      // flickers as the cursor crosses the hero is worse than no hover behaviour.
      onMouseEnter={() => setSuspended(true)}
      onMouseLeave={() => setSuspended(false)}
      onFocus={() => setSuspended(true)}
      onBlur={() => setSuspended(false)}
    >
      <ul
        className="hero-track flex h-full w-full list-none"
        style={{ transform: `translate3d(-${index * 100}%, 0, 0)` }}
      >
        {slides.map((slide, i) => (
          <li
            key={slide.clip}
            role="group"
            aria-roledescription="slide"
            aria-label={`${i + 1} / ${count}`}
            aria-hidden={i !== index}
            // Without `inert` the off-screen headlines stay in the tab order and in the
            // accessibility tree — three h2s a screen-reader user cannot see.
            inert={i !== index}
            className="relative h-full w-full shrink-0"
          >
            <Image
              src={posterSrc(slide.clip)}
              alt=""
              fill
              sizes="100vw"
              // The LCP element. Next 16 replaced `priority` with `preload`.
              preload={i === 0}
              className="object-cover"
            />
            {carriesVideo(i) && sources[i] ? (
              <video
                ref={(el) => {
                  videos.current[i] = el;
                }}
                src={sources[i] ?? undefined}
                muted
                loop
                playsInline
                /*
                 * Only the slide that is playing may buffer. The next one mounts so its
                 * connection and headers are warm, but `metadata` stops it pulling media
                 * data it may never show — which matters more than usual while the hosted
                 * files are the untranscoded originals (see lib/media.ts): "auto" on a
                 * 38 MB 4K clip would have the browser buffering ahead the whole time the
                 * previous slide is on screen.
                 */
                preload={i === index ? "auto" : "metadata"}
                aria-hidden="true"
                tabIndex={-1}
                disablePictureInPicture
                className="absolute inset-0 h-full w-full object-cover"
              />
            ) : null}
          </li>
        ))}
      </ul>

      <div className="hero-scrim pointer-events-none absolute inset-0" />

      <div className="absolute inset-0 flex flex-col justify-end">
        <div className="mx-auto w-full max-w-7xl px-6 pb-10 md:px-10 md:pb-14">
          {/* The copy is real text over the footage, never baked into the video: it has to
              translate, scale, and be readable by a screen reader. */}
          <p className="eyebrow text-primary-foreground/75">{slides[index]?.eyebrow}</p>
          <h1 className="title-page mt-3 max-w-3xl text-[2rem] text-primary-foreground md:text-[3.25rem]">
            {slides[index]?.headline}
          </h1>

          <div className="mt-8 flex items-center gap-5">
            <button
              type="button"
              onClick={() => setPaused((p) => !p)}
              aria-label={paused ? labels.play : labels.pause}
              className="hero-control h-10 w-10"
            >
              {paused ? <PlayGlyph /> : <PauseGlyph />}
            </button>

            <div className="flex items-center gap-2">
              {slides.map((slide, i) => (
                <button
                  key={slide.clip}
                  type="button"
                  onClick={() => {
                    setPaused(true);
                    setIndex(i);
                  }}
                  aria-label={`${labels.goToSlide} ${i + 1}`}
                  aria-current={i === index}
                  className={`h-[3px] w-10 transition-[background-color] duration-150 ${
                    i === index ? "bg-accent" : "bg-primary-foreground/35"
                  }`}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function PauseGlyph() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <rect x="6" y="4" width="4" height="16" rx="1" />
      <rect x="14" y="4" width="4" height="16" rx="1" />
    </svg>
  );
}

function PlayGlyph() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M8 5v14l11-7L8 5Z" />
    </svg>
  );
}
