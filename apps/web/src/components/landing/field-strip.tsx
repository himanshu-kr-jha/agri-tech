"use client";

/**
 * The two-up strip: advisory reaching a farmer, and a field officer with a member.
 *
 * These are the other two clips. They are 768×432 and carry burned-in stock-library comp
 * watermarks, which is why they play here at their native size rather than in the hero —
 * upscaled to a full-bleed 1280px they would be both soft and unmissably marked. The mark
 * is centred in frame and cannot be cropped out at any usable framing; that was measured,
 * not assumed. See ADR-0025, which also records the swap path: replacing the two files
 * changes no code.
 *
 * Client-side for two reasons, both about not taking something from the visitor. An
 * `autoPlay loop` video would start playing for someone who has asked for reduced motion,
 * and would download both clips the moment the page loads — even though this section sits
 * well below the fold and many visitors never reach it. An IntersectionObserver buys back
 * both.
 */

import Image from "next/image";
import { useEffect, useRef, useState } from "react";

import { posterSrc, videoSrc } from "@/lib/media";

export type StripItem = { clip: string; caption: string };

export function FieldStrip({ eyebrow, items }: { eyebrow: string; items: StripItem[] }) {
  const container = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(false);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const node = container.current;
    if (!node) return;

    const observer = new IntersectionObserver(
      ([entry]) => setActive(entry?.isIntersecting ?? false),
      { rootMargin: "200px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <section ref={container} className="border-t border-border/70">
      <div className="mx-auto w-full max-w-7xl px-6 py-16 md:px-10 md:py-20">
        <p className="eyebrow">{eyebrow}</p>

        <div className="mt-8 grid gap-4 md:grid-cols-2">
          {items.map((item) => {
            const src = active ? videoSrc(item.clip) : null;
            return (
              <figure key={item.clip}>
                <div className="relative aspect-video overflow-hidden rounded-md border border-border/70 bg-muted">
                  <Image
                    src={posterSrc(item.clip)}
                    alt=""
                    fill
                    sizes="(min-width: 768px) 50vw, 100vw"
                    className="object-cover"
                  />
                  {src ? (
                    <video
                      src={src}
                      autoPlay
                      muted
                      loop
                      playsInline
                      preload="none"
                      aria-hidden="true"
                      tabIndex={-1}
                      disablePictureInPicture
                      className="absolute inset-0 h-full w-full object-cover"
                    />
                  ) : null}
                </div>
                <figcaption className="mt-3 text-sm leading-relaxed text-muted-foreground">
                  {item.caption}
                </figcaption>
              </figure>
            );
          })}
        </div>
      </div>
    </section>
  );
}
