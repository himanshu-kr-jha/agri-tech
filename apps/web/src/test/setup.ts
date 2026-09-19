/**
 * jsdom shims for the landing page's client components.
 *
 * jsdom has no `matchMedia` and no `IntersectionObserver`, and its `HTMLMediaElement.play`
 * throws "Not implemented". All three are things the hero legitimately depends on, so the
 * choice is to stub them here or to not test the component that carries the most logic on
 * the page. `setMatchMedia` lets a test answer a specific query — which is how the
 * reduced-motion behaviour gets asserted rather than assumed.
 */

import { vi } from "vitest";

type QueryAnswers = Record<string, boolean>;

/** Default: a wide screen, no reduced-motion preference — the "gets video" case. */
let answers: QueryAnswers = {
  "(prefers-reduced-motion: reduce)": false,
  "(min-width: 768px)": true,
};

export function setMatchMedia(next: QueryAnswers) {
  answers = { ...answers, ...next };
}

export function resetMatchMedia() {
  answers = {
    "(prefers-reduced-motion: reduce)": false,
    "(min-width: 768px)": true,
  };
}

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: answers[query] ?? false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
});

class NoopObserver implements IntersectionObserver {
  readonly root = null;
  readonly rootMargin = "";
  readonly thresholds: ReadonlyArray<number> = [];
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
  takeRecords = () => [];
}
vi.stubGlobal("IntersectionObserver", NoopObserver);

HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
HTMLMediaElement.prototype.pause = vi.fn();
