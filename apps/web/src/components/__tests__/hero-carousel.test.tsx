/**
 * The hero carousel's contracts — ADR-0025.
 *
 * These are the properties that are expensive to notice by looking: nobody spots a third
 * clip being downloaded, or an off-screen headline sitting in the tab order, or autoplay
 * quietly overriding a reduced-motion preference. They are cheap to assert.
 */

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HeroCarousel, type Slide } from "@/components/landing/hero-carousel";
import { resetMatchMedia, setMatchMedia } from "@/test/setup";

const SLIDES: Slide[] = [
  { clip: "hero-01-paddy", eyebrow: "Where it begins", headline: "First line." },
  { clip: "hero-02-grading", eyebrow: "Where it adds up", headline: "Second line." },
  { clip: "hero-03-harvest", eyebrow: "Where it is settled", headline: "Third line." },
];

const LABELS = {
  carousel: "AgriVardhak in the field",
  pause: "Pause video",
  play: "Play video",
  goToSlide: "Go to slide",
};

function renderHero() {
  return render(<HeroCarousel slides={SLIDES} labels={LABELS} />);
}

const track = (container: HTMLElement) => container.querySelector(".hero-track") as HTMLElement;

afterEach(() => {
  cleanup();
  resetMatchMedia();
  vi.useRealTimers();
});

describe("the hero carousel", () => {
  it("renders no video element at all on first paint", () => {
    // The hydration contract and the mobile default in one assertion. The server cannot
    // know the viewport, the connection or the motion preference, so the first client
    // render must match the HTML: posters only, video as a later upgrade.
    const { container } = renderHero();
    expect(container.querySelector("video")).toBeNull();
  });

  it("shows every slide's poster, so nothing depends on the CDN", () => {
    const { container } = renderHero();
    expect(container.querySelectorAll("img")).toHaveLength(SLIDES.length);
  });

  it("keeps the off-screen slides out of the accessibility tree and the tab order", () => {
    const { container } = renderHero();
    const slides = container.querySelectorAll('[aria-roledescription="slide"]');

    // The attribute, not the property: jsdom does not implement `inert`, though React
    // does emit it. The attribute is what the browser and assistive tech act on anyway.
    expect(slides[0]?.hasAttribute("inert")).toBe(false);
    expect(slides[0]?.getAttribute("aria-hidden")).toBe("false");
    for (const hidden of [slides[1], slides[2]]) {
      expect(hidden?.hasAttribute("inert")).toBe(true);
      expect(hidden?.getAttribute("aria-hidden")).toBe("true");
    }
  });

  it("moves the track by one full width per slide", () => {
    const { container } = renderHero();
    expect(track(container).style.transform).toBe("translate3d(-0%, 0, 0)");

    fireEvent.click(screen.getByLabelText(`${LABELS.goToSlide} 3`));
    expect(track(container).style.transform).toBe("translate3d(-200%, 0, 0)");
  });

  it("marks exactly one indicator as current", () => {
    renderHero();
    fireEvent.click(screen.getByLabelText(`${LABELS.goToSlide} 2`));

    const current = SLIDES.map(
      (_, i) => screen.getByLabelText(`${LABELS.goToSlide} ${i + 1}`).getAttribute("aria-current"),
    );
    expect(current).toEqual(["false", "true", "false"]);
  });

  it("swaps the control's accessible name rather than relying on the glyph alone", () => {
    renderHero();
    fireEvent.click(screen.getByLabelText(LABELS.pause));
    expect(screen.getByLabelText(LABELS.play)).toBeTruthy();
  });

  it("advances on its own", () => {
    vi.useFakeTimers();
    const { container } = renderHero();

    act(() => void vi.advanceTimersByTime(6500));
    expect(track(container).style.transform).toBe("translate3d(-100%, 0, 0)");
  });

  it("does not advance once paused", () => {
    vi.useFakeTimers();
    const { container } = renderHero();

    fireEvent.click(screen.getByLabelText(LABELS.pause));
    act(() => void vi.advanceTimersByTime(30_000));
    expect(track(container).style.transform).toBe("translate3d(-0%, 0, 0)");
  });

  it("never autoplays for a visitor who asked for reduced motion", () => {
    setMatchMedia({ "(prefers-reduced-motion: reduce)": true });
    vi.useFakeTimers();
    const { container } = renderHero();

    act(() => void vi.advanceTimersByTime(30_000));
    expect(track(container).style.transform).toBe("translate3d(-0%, 0, 0)");
    // …but the slides are still reachable by hand.
    expect(screen.getByLabelText(LABELS.play)).toBeTruthy();
  });

  it("stops rotating as soon as the visitor steps through it themselves", () => {
    vi.useFakeTimers();
    const { container } = renderHero();

    fireEvent.keyDown(container.querySelector('[aria-roledescription="carousel"]')!, {
      key: "ArrowRight",
    });
    expect(track(container).style.transform).toBe("translate3d(-100%, 0, 0)");

    act(() => void vi.advanceTimersByTime(30_000));
    expect(track(container).style.transform).toBe("translate3d(-100%, 0, 0)");
  });
});

describe("when no video CDN is configured", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_VIDEO_BASE_URL", "");
  });
  afterEach(() => vi.unstubAllEnvs());

  it("still renders a working carousel, as posters", () => {
    // `make seed && make dev` with no network is a supported mode, not a broken one.
    const { container } = renderHero();
    expect(container.querySelector("video")).toBeNull();
    expect(container.querySelectorAll("img")).toHaveLength(SLIDES.length);
    expect(screen.getByText("First line.")).toBeTruthy();
  });
});
