/**
 * The page translator engine — reads the text off a live DOM, translates it, and writes it
 * back in place (ADR-0023, UI-11).
 *
 * **It changes the language layer, never the structure.** Only two writes exist in this file:
 * `Text.nodeValue` and `Element.setAttribute` for a short allowlist of human-readable
 * attributes. No `innerHTML`, so a translation containing `<script>` is inert text; and no
 * node is ever replaced, so React keeps the references it reconciles against.
 *
 * **The source language is read from the script, per string.** Devanagari is Hindi, Latin
 * is English. One page can hold both — an English console showing a published Hindi order —
 * and whichever direction the reader asks for, only the text that is not already in that
 * language moves.
 *
 * **The original is remembered.** Every slot keeps the text it had before we touched it.
 * Switching back restores that text with no network call (NFR-505). If React (or anything
 * else) writes a new value, it no longer matches what we wrote, so it becomes the new
 * original and is translated in its turn.
 *
 * Resolution order per string: static dictionary → local cache → one batched request. A
 * string that failed is not retried on every mutation; `retry()` clears that.
 *
 * The document `<title>` is not translated: in this app it is the product name, and Sarvam
 * rendered "AgriVardhak" as "पौष्टिक" ("nutritious") in the browser tab.
 *
 * Pure DOM + an injected `fetchTranslations`, so it runs under jsdom in tests.
 */

import { normaliseText } from "@/lib/i18n";
import type { Locale } from "@/lib/locale";

export type Lang = "en-IN" | "hi-IN";

export const LANG_FOR_LOCALE: Record<Locale, Lang> = { en: "en-IN", hi: "hi-IN" };

/**
 * Subtrees that are never translated. `translate="no"` is the HTML standard for exactly
 * this; `font-mono` is how this codebase marks identifiers (packet ids, hashes, file paths).
 */
export const SKIP_SELECTOR = [
  "script",
  "style",
  "noscript",
  "template",
  "code",
  "pre",
  "kbd",
  "samp",
  "textarea",
  "svg",
  "[contenteditable]",
  '[translate="no"]',
  "[data-no-translate]",
  ".font-mono",
].join(",");

export const TRANSLATED_ATTRIBUTES = ["placeholder", "aria-label", "title", "alt"] as const;

const DEVANAGARI = /[\u0900-\u097F]/g;
const LATIN = /[A-Za-z]/g;
const HAS_LETTER = /[A-Za-z\u0900-\u097F]/;
const URL_LIKE = /^(https?:\/\/|www\.)\S+$/i;
const EMAIL_LIKE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const UUID_LIKE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const HASH_LIKE = /^(?=.*\d)[0-9a-f]{12,}$/i;
/** Requirement ids and codes: FR-812, INV-1, SHA-256, seed/sources.md. */
const CODE_LIKE = /^[A-Za-z0-9]+([-_./:][A-Za-z0-9]+)+$/;

export function detectLang(text: string): Lang | null {
  const devanagari = text.match(DEVANAGARI)?.length ?? 0;
  const latin = text.match(LATIN)?.length ?? 0;
  if (devanagari === 0 && latin === 0) return null;
  // Weighted: a Devanagari word spends more code points on fewer letters than an English one
  // does, and a Hindi sentence that names "AgriVardhak" is still a Hindi sentence.
  return devanagari * 1.5 >= latin ? "hi-IN" : "en-IN";
}

/**
 * Every digit sequence in the source survives in the translation. The API already enforces
 * this; checking again here means a stale browser cache can never put a wrong number on
 * screen either. ("205 kg" once came back as "बीस किलो" — twenty kg.)
 */
export function numbersKept(source: string, translated: string): boolean {
  const digits = (text: string) =>
    (text.replace(/(?<=\d),(?=\d)/g, "").match(/\d+/g) ?? []).sort();
  const wanted = digits(source);
  const got = digits(translated);
  const counts = new Map<string, number>();
  for (const d of got) counts.set(d, (counts.get(d) ?? 0) + 1);
  return wanted.every((d) => {
    const n = counts.get(d) ?? 0;
    counts.set(d, n - 1);
    return n > 0;
  });
}

/**
 * A translation may be shown: numbers intact, and actually in the target language. Mirrors
 * `acceptable` in the API — a stale browser cache must not be looser than the server.
 */
export function acceptable(source: string, translated: string, target: Lang): boolean {
  // Unchanged means the API resolved it as needing no translation ("A" in "Grade A").
  if (normaliseText(translated) === normaliseText(source)) return true;
  if (!numbersKept(source, translated)) return false;
  // English may contain no Devanagari; Hindi may contain Latin (DAP, PM-KISAN, Sarjoo-52).
  if (target === "en-IN") return !/[\u0900-\u097F]/.test(translated);
  const lang = detectLang(translated);
  return lang === null || lang === "hi-IN";
}

/** Is this worth sending? Numbers, links, ids and codes are not language. */
export function isTranslatable(text: string): boolean {
  const t = normaliseText(text);
  if (!t || !HAS_LETTER.test(t)) return false;
  if (URL_LIKE.test(t) || EMAIL_LIKE.test(t) || UUID_LIKE.test(t) || HASH_LIKE.test(t)) {
    return false;
  }
  // A code is a single token with separators and at least one digit or a path/extension.
  if (!t.includes(" ") && CODE_LIKE.test(t) && /[\d/.]/.test(t)) return false;
  return true;
}

// --------------------------------------------------------------------------- cache

/** Bumped whenever acceptance tightens: older entries may hold a changed number (v1) or a
 *  half-translated line (v2); v3 stored a bare array. Glossary edits are handled by
 *  `useCorpusVersion` instead. */
const STORAGE_KEY = "agri-translation-cache-v4";
const MAX_CACHE_ENTRIES = 3000;

/**
 * Memory first, `localStorage` second. Storage is a convenience: it may be absent, full, or
 * throw in a private window, and the translator must behave identically without it.
 */
export class TranslationCache {
  private entries = new Map<string, string>();
  private corpusVersion: string | null = null;
  private persistTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(private readonly persistent = true) {
    if (!persistent) return;
    try {
      const raw = globalThis.localStorage?.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as { version: string | null; entries: [string, string][] };
        this.corpusVersion = parsed.version ?? null;
        this.entries = new Map((parsed.entries ?? []).slice(-MAX_CACHE_ENTRIES));
      }
    } catch {
      this.entries = new Map();
    }
  }

  /**
   * The API reports which glossary its translations obey. When that changes, every cached
   * rendering may use a term the glossary no longer allows ("समिति" for FPO), so start over.
   */
  useCorpusVersion(version: string): boolean {
    if (!version || this.corpusVersion === version) return false;
    // Entries saved under another glossary — or under none recorded — cannot be trusted.
    const stale = this.entries.size > 0;
    this.entries.clear();
    this.corpusVersion = version;
    this.schedulePersist();
    return stale;
  }

  get(target: Lang, text: string): string | undefined {
    return this.entries.get(`${target}|${text}`);
  }

  set(target: Lang, text: string, translated: string): void {
    const key = `${target}|${text}`;
    this.entries.delete(key);
    this.entries.set(key, translated);
    while (this.entries.size > MAX_CACHE_ENTRIES) {
      const oldest = this.entries.keys().next().value;
      if (oldest === undefined) break;
      this.entries.delete(oldest);
    }
    this.schedulePersist();
  }

  private schedulePersist(): void {
    if (!this.persistent || this.persistTimer) return;
    this.persistTimer = setTimeout(() => {
      this.persistTimer = null;
      try {
        globalThis.localStorage?.setItem(
          STORAGE_KEY,
          JSON.stringify({ version: this.corpusVersion, entries: [...this.entries] }),
        );
      } catch {
        // Quota or privacy mode. The in-memory cache still works for this page.
      }
    }, 1000);
  }
}

// --------------------------------------------------------------------------- engine

type Slot =
  | { kind: "text"; node: Text }
  | { kind: "attr"; element: Element; name: string };

interface Memo {
  original: string;
  applied: string | null;
}

export interface TranslatorStatus {
  /** Requests in flight. */
  busy: boolean;
  /** Strings that could not be translated for the current target. */
  failed: number;
}

export interface PageTranslatorOptions {
  root: HTMLElement;
  target: Lang;
  /**
   * One entry per text: the translation, or `null` when the API could not translate it (as
   * opposed to returning it unchanged because it needed no translation).
   */
  fetchTranslations: (texts: string[], target: Lang) => Promise<(string | null)[]>;
  dictionary?: { toHindi: Map<string, string>; toEnglish: Map<string, string> };
  cache?: TranslationCache;
  /** Quiet period before new or changed content is translated. Streams settle first. */
  debounceMs?: number;
  maxBatchTexts?: number;
  maxBatchChars?: number;
  /** Delay before failed strings are retried once automatically. */
  autoRetryMs?: number;
  onStatus?: (status: TranslatorStatus) => void;
}

/**
 * One batch at a time. The API already fans each batch out to Sarvam; three batches in
 * parallel on a large page tripped Sarvam's rate limit for the whole key (measured).
 */
const MAX_PARALLEL_REQUESTS = 1;

/** Strings that failed are tried once more on their own after this long — a rate-limit
 *  window has usually passed, and nobody should have to find the retry button for that. */
const AUTO_RETRY_MS = 20_000;

export class PageTranslator {
  private target: Lang;
  private readonly root: HTMLElement;
  private readonly fetchTranslations: PageTranslatorOptions["fetchTranslations"];
  private readonly dictionary: NonNullable<PageTranslatorOptions["dictionary"]>;
  private readonly cache: TranslationCache;
  private readonly debounceMs: number;
  private readonly maxBatchTexts: number;
  private readonly maxBatchChars: number;
  private readonly autoRetryMs: number;
  private readonly onStatus?: (status: TranslatorStatus) => void;

  private readonly textMemo = new WeakMap<Text, Memo>();
  private readonly attrMemo = new WeakMap<Element, Map<string, Memo>>();

  /** normalised text → slots waiting for it, for the current target. */
  private queue = new Map<string, Slot[]>();
  /** `${target}|${text}` currently requested. */
  private inFlight = new Set<string>();
  private failed = new Set<string>();
  private requests = 0;

  private observer: MutationObserver | null = null;
  private running = false;
  private pendingRoots = new Set<Node>();
  private debounceTimer: ReturnType<typeof setTimeout> | null = null;
  private idle: Promise<void> = Promise.resolve();
  private autoRetryTimer: ReturnType<typeof setTimeout> | null = null;
  private autoRetried = false;

  constructor(options: PageTranslatorOptions) {
    this.root = options.root;
    this.target = options.target;
    this.fetchTranslations = options.fetchTranslations;
    this.dictionary = options.dictionary ?? { toHindi: new Map(), toEnglish: new Map() };
    this.cache = options.cache ?? new TranslationCache(false);
    this.debounceMs = options.debounceMs ?? 300;
    this.maxBatchTexts = options.maxBatchTexts ?? 50;
    this.maxBatchChars = options.maxBatchChars ?? 8000;
    this.autoRetryMs = options.autoRetryMs ?? AUTO_RETRY_MS;
    this.onStatus = options.onStatus;
  }

  /** Translate what is on screen now, and keep translating what appears later. */
  start(): Promise<void> {
    this.running = true;
    if (!this.observer && typeof MutationObserver !== "undefined") {
      this.observer = new MutationObserver((records) => this.onMutations(records));
      this.observer.observe(this.root, {
        childList: true,
        subtree: true,
        characterData: true,
        attributes: true,
        attributeFilter: [...TRANSLATED_ATTRIBUTES],
      });
    }
    return this.translateNow(this.root);
  }

  /**
   * Stop observing and writing. Remembered originals are kept, so `start()` on the same
   * instance resumes correctly — which is why the provider keeps one instance per document
   * rather than one per mount.
   */
  stop(): void {
    this.running = false;
    this.observer?.disconnect();
    this.observer = null;
    if (this.debounceTimer) clearTimeout(this.debounceTimer);
    this.debounceTimer = null;
    if (this.autoRetryTimer) clearTimeout(this.autoRetryTimer);
    this.autoRetryTimer = null;
    this.pendingRoots.clear();
  }

  setTarget(target: Lang): Promise<void> {
    this.target = target;
    this.queue.clear();
    this.autoRetried = false;
    return this.translateNow(this.root);
  }

  getTarget(): Lang {
    return this.target;
  }

  /** Re-resolve every slot from its original — after the cache was cleared underneath us. */
  refresh(): Promise<void> {
    return this.setTarget(this.target);
  }

  /** Forget failures and try the whole page again. */
  retry(): Promise<void> {
    this.failed.clear();
    this.emitStatus();
    return this.translateNow(this.root);
  }

  /** Resolves when every request started so far has settled. For tests and for the toggle. */
  async whenIdle(): Promise<void> {
    let seen: Promise<void> | null = null;
    while (seen !== this.idle) {
      seen = this.idle;
      await seen;
    }
  }

  // ---------------------------------------------------------------- scanning

  private translateNow(root: Node): Promise<void> {
    this.scan(root);
    this.dispatchQueue();
    return this.whenIdle();
  }

  private onMutations(records: MutationRecord[]): void {
    for (const record of records) {
      if (record.type === "childList") {
        record.addedNodes.forEach((node) => this.pendingRoots.add(node));
      } else {
        this.pendingRoots.add(record.target);
      }
    }
    if (this.debounceTimer) clearTimeout(this.debounceTimer);
    this.debounceTimer = setTimeout(() => {
      this.debounceTimer = null;
      const roots = [...this.pendingRoots];
      this.pendingRoots.clear();
      for (const node of roots) {
        if (node.isConnected) this.scan(node);
      }
      this.dispatchQueue();
    }, this.debounceMs);
  }

  private scan(start: Node): void {
    if (start.nodeType === Node.TEXT_NODE) {
      const parent = start.parentElement;
      if (parent && !parent.closest(SKIP_SELECTOR)) this.process({ kind: "text", node: start as Text });
      return;
    }
    if (start.nodeType !== Node.ELEMENT_NODE) return;
    const element = start as Element;
    if (element.closest(SKIP_SELECTOR)) return;

    const walker = element.ownerDocument.createTreeWalker(
      element,
      NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT,
      {
        acceptNode: (node) =>
          node.nodeType === Node.ELEMENT_NODE && (node as Element).matches(SKIP_SELECTOR)
            ? NodeFilter.FILTER_REJECT
            : NodeFilter.FILTER_ACCEPT,
      },
    );
    for (let node: Node | null = walker.currentNode; node; node = walker.nextNode()) {
      if (node.nodeType === Node.TEXT_NODE) {
        this.process({ kind: "text", node: node as Text });
      } else {
        for (const name of TRANSLATED_ATTRIBUTES) {
          if ((node as Element).hasAttribute(name)) {
            this.process({ kind: "attr", element: node as Element, name });
          }
        }
      }
    }
  }

  // ---------------------------------------------------------------- one slot

  private read(slot: Slot): string {
    return slot.kind === "text"
      ? (slot.node.nodeValue ?? "")
      : (slot.element.getAttribute(slot.name) ?? "");
  }

  private write(slot: Slot, value: string): void {
    if (!this.running || this.read(slot) === value) return;
    if (slot.kind === "text") slot.node.nodeValue = value;
    else slot.element.setAttribute(slot.name, value);
  }

  private memo(slot: Slot): Memo {
    const current = this.read(slot);
    let memo: Memo | undefined;
    if (slot.kind === "text") {
      memo = this.textMemo.get(slot.node);
    } else {
      memo = this.attrMemo.get(slot.element)?.get(slot.name);
    }
    if (!memo || (current !== memo.applied && current !== memo.original)) {
      memo = { original: current, applied: null };
      if (slot.kind === "text") {
        this.textMemo.set(slot.node, memo);
      } else {
        const perElement = this.attrMemo.get(slot.element) ?? new Map<string, Memo>();
        perElement.set(slot.name, memo);
        this.attrMemo.set(slot.element, perElement);
      }
    }
    return memo;
  }

  private process(slot: Slot): void {
    const memo = this.memo(slot);
    const source = memo.original;
    const text = normaliseText(source);
    if (!isTranslatable(text)) return;

    // The dictionary knows which language its own entries are in; the script heuristic is
    // only for text it has never seen.
    const lang = this.dictionary.toHindi.has(text)
      ? "en-IN"
      : this.dictionary.toEnglish.has(text)
        ? "hi-IN"
        : detectLang(text);
    if (lang === null) return;
    if (lang === this.target) {
      memo.applied = null;
      this.write(slot, source);
      return;
    }

    const hit = this.lookup(text);
    if (hit !== undefined && acceptable(text, hit, this.target)) {
      const value = withSurroundingWhitespace(source, hit);
      memo.applied = value;
      this.write(slot, value);
      return;
    }
    if (this.failed.has(`${this.target}|${text}`)) return;

    const waiting = this.queue.get(text);
    if (waiting) waiting.push(slot);
    else this.queue.set(text, [slot]);
  }

  private lookup(text: string): string | undefined {
    const dictionary = this.target === "hi-IN" ? this.dictionary.toHindi : this.dictionary.toEnglish;
    return dictionary.get(text) ?? this.cache.get(this.target, text);
  }

  // ---------------------------------------------------------------- network

  private dispatchQueue(): void {
    const target = this.target;
    const texts = [...this.queue.keys()].filter((t) => !this.inFlight.has(`${target}|${t}`));
    if (texts.length === 0) return;

    const batches: string[][] = [];
    let batch: string[] = [];
    let chars = 0;
    for (const text of texts) {
      if (batch.length && (batch.length >= this.maxBatchTexts || chars + text.length > this.maxBatchChars)) {
        batches.push(batch);
        batch = [];
        chars = 0;
      }
      batch.push(text);
      chars += text.length;
      this.inFlight.add(`${target}|${text}`);
    }
    if (batch.length) batches.push(batch);

    const run = async () => {
      for (let i = 0; i < batches.length; i += MAX_PARALLEL_REQUESTS) {
        await Promise.all(batches.slice(i, i + MAX_PARALLEL_REQUESTS).map((b) => this.request(b, target)));
      }
    };
    const previous = this.idle;
    this.idle = Promise.all([previous, run()]).then(() => undefined);
  }

  private async request(texts: string[], target: Lang): Promise<void> {
    this.requests += 1;
    this.emitStatus();
    let translations: (string | null)[] | null = null;
    try {
      const result = await this.fetchTranslations(texts, target);
      if (Array.isArray(result) && result.length === texts.length) translations = result;
    } catch {
      translations = null;
    } finally {
      this.requests -= 1;
    }

    texts.forEach((text, i) => {
      this.inFlight.delete(`${target}|${text}`);
      const translated = translations?.[i];
      // `null` is the API saying it could not translate this; caching the source would pin
      // the page in the wrong language. An unchanged string it *did* resolve ("A" in
      // "Grade A") is cached like any other, so it is not asked for again.
      if (translated && acceptable(text, translated, target)) {
        this.cache.set(target, text, translated);
      } else {
        this.failed.add(`${target}|${text}`);
      }
      if (target !== this.target) return;
      const slots = this.queue.get(text) ?? [];
      this.queue.delete(text);
      for (const slot of slots) {
        const connected = slot.kind === "text" ? slot.node.isConnected : slot.element.isConnected;
        if (connected) this.process(slot);
      }
    });
    this.emitStatus();
  }

  private emitStatus(): void {
    let failed = 0;
    for (const key of this.failed) if (key.startsWith(`${this.target}|`)) failed += 1;
    this.onStatus?.({ busy: this.requests > 0, failed });
    if (failed > 0 && this.requests === 0 && !this.autoRetried && !this.autoRetryTimer && this.running) {
      this.autoRetryTimer = setTimeout(() => {
        this.autoRetryTimer = null;
        this.autoRetried = true;
        void this.retry();
      }, this.autoRetryMs);
    }
  }
}

/** Keep the source's leading and trailing whitespace — JSX spacing lives in those. */
export function withSurroundingWhitespace(source: string, translated: string): string {
  const leading = source.match(/^\s*/)?.[0] ?? "";
  const trailing = source.match(/\s*$/)?.[0] ?? "";
  return `${leading}${translated.trim()}${trailing}`;
}
