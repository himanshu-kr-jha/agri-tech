/**
 * The page translator engine — UI-11, NFR-304, NFR-505, ADR-0023.
 *
 * What these protect: structure is never touched (only text values and an attribute
 * allowlist change), protected subtrees stay as they are, switching back costs no request,
 * content that appears later is translated once it settles, and a failed request leaves the
 * source text on screen.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  PageTranslator,
  TranslationCache,
  detectLang,
  isTranslatable,
  numbersKept,
  type Lang,
} from "@/lib/dom-translate";
import { dictionaryLookups } from "@/lib/i18n";

type Fetch = (texts: string[], target: Lang) => Promise<(string | null)[]>;

/**
 * A fake API: English → "हिन्दीअनुवादकिया(<text>)", Hindi → "TRANSLATED(<n> chars)". The markers
 * are long enough to dominate the script of the wrapped text, because the translator rejects
 * output that is not actually in the target language. Records every call.
 */
function fakeApi() {
  const calls: { texts: string[]; target: Lang }[] = [];
  const fetchTranslations = vi.fn<Fetch>(async (texts, target) => {
    calls.push({ texts: [...texts], target });
    // English output may carry no Devanagari, so the Hindi source is not echoed inside it.
    return texts.map((t) =>
      target === "hi-IN" ? `हिन्दीअनुवादकिया(${t})` : `TRANSLATED(${[...t].length} chars)`,
    );
  });
  return { calls, fetchTranslations };
}

function mount(html: string): HTMLElement {
  document.body.innerHTML = `<main id="root">${html}</main>`;
  return document.getElementById("root") as HTMLElement;
}

function make(root: HTMLElement, fetchTranslations: Fetch, target: Lang = "hi-IN", extra = {}) {
  return new PageTranslator({
    root,
    target,
    fetchTranslations,
    cache: new TranslationCache(false),
    debounceMs: 20,
    ...extra,
  });
}

const settle = (ms = 60) => new Promise((resolve) => setTimeout(resolve, ms));

afterEach(() => {
  document.body.innerHTML = "";
});

describe("what counts as translatable", () => {
  it("reads the script, weighting Devanagari", () => {
    expect(detectLang("My crops")).toBe("en-IN");
    expect(detectLang("मेरी फ़सल")).toBe("hi-IN");
    expect(detectLang("AgriVardhak सुझाव देता है।")).toBe("hi-IN");
    expect(detectLang("82% · 12.5")).toBeNull();
  });

  it("checks numbers survive, ignoring digit grouping", () => {
    expect(numbersKept("₹1,20,000 for 2.5 acres", "2.5 एकड़ के लिए ₹120000")).toBe(true);
    expect(numbersKept("205 kg", "बीस किलो")).toBe(false);
    expect(numbersKept("5 and 5", "5")).toBe(false);
  });

  it("skips numbers, links, emails, ids and codes", () => {
    for (const text of [
      "42",
      "₹ 1,20,000",
      "https://agrivardhak.dev/x",
      "ceo@fpo.in",
      "0192f0c4-6a8e-7d3b-9c1a-2b3c4d5e6f70",
      "a3f9c2d17b4e8f60",
      "FR-812",
      "seed/sources.md",
    ]) {
      expect(isTranslatable(text), text).toBe(false);
    }
    expect(isTranslatable("Expected harvest")).toBe(true);
    expect(isTranslatable("FPO")).toBe(true);
    // Units are sent: the API renders them from its glossary ("1.48 ac" → "1.48 एकड़").
    expect(isTranslatable("1.48 ac")).toBe(true);
    expect(isTranslatable("Expected 4.2 tonnes")).toBe(true);
  });
});

describe("PageTranslator", () => {
  let api: ReturnType<typeof fakeApi>;
  beforeEach(() => {
    api = fakeApi();
  });

  it("translates text and attributes in place without changing structure", async () => {
    const root = mount(
      `<h1>Crop health</h1><p>Paddy <strong>ready</strong> soon</p>` +
        `<input placeholder="Search notices" value="typed by user" />` +
        `<button aria-label="Close panel" title="Close">x</button>`,
    );
    const before = root.querySelectorAll("*").length;
    const heading = root.querySelector("h1")!.firstChild;
    const translator = make(root, api.fetchTranslations);

    await translator.start();

    expect(root.querySelector("h1")!.textContent).toBe("हिन्दीअनुवादकिया(Crop health)");
    // Same node object: React's reference survives.
    expect(root.querySelector("h1")!.firstChild).toBe(heading);
    expect(root.querySelector("p")!.textContent).toBe("हिन्दीअनुवादकिया(Paddy) हिन्दीअनुवादकिया(ready) हिन्दीअनुवादकिया(soon)");
    const input = root.querySelector("input")!;
    expect(input.getAttribute("placeholder")).toBe("हिन्दीअनुवादकिया(Search notices)");
    expect(input.value).toBe("typed by user");
    expect(root.querySelector("button")!.getAttribute("aria-label")).toBe("हिन्दीअनुवादकिया(Close panel)");
    expect(root.querySelector("button")!.getAttribute("title")).toBe("हिन्दीअनुवादकिया(Close)");
    expect(root.querySelectorAll("*").length).toBe(before);
    translator.stop();
  });

  it("keeps the whitespace JSX spacing lives in", async () => {
    const root = mount(`<p>  Grade </p>`);
    const translator = make(root, api.fetchTranslations);
    await translator.start();
    expect(root.querySelector("p")!.firstChild!.nodeValue).toBe("  हिन्दीअनुवादकिया(Grade) ");
    translator.stop();
  });

  it("never enters protected subtrees", async () => {
    const root = mount(
      `<h1 translate="no">Ramesh Prajapati</h1>` +
        `<span data-no-translate>Keep me</span>` +
        `<code>make seed</code><pre>raw output</pre>` +
        `<span class="font-mono">packet ab12</span>` +
        `<textarea>draft question</textarea>` +
        `<p>Village</p>`,
    );
    const translator = make(root, api.fetchTranslations);
    await translator.start();

    const sent = api.calls.flatMap((c) => c.texts);
    expect(sent).toEqual(["Village"]);
    expect(root.querySelector("h1")!.textContent).toBe("Ramesh Prajapati");
    expect(root.querySelector("code")!.textContent).toBe("make seed");
    translator.stop();
  });

  it("batches and de-duplicates: one request for repeated strings", async () => {
    const root = mount(`<p>Seed</p><p>Seed</p><p>Market</p>`);
    const translator = make(root, api.fetchTranslations);
    await translator.start();
    expect(api.calls).toHaveLength(1);
    expect(api.calls[0].texts.sort()).toEqual(["Market", "Seed"]);
    translator.stop();
  });

  it("splits requests under the batch caps", async () => {
    const root = mount(
      Array.from({ length: 7 }, (_, i) => `<p>Item number ${"abcdefg"[i]}</p>`).join(""),
    );
    const translator = make(root, api.fetchTranslations, "hi-IN", { maxBatchTexts: 3 });
    await translator.start();
    // Sent one batch at a time, never in parallel.
    expect(api.calls.map((c) => c.texts.length)).toEqual([3, 3, 1]);
    translator.stop();
  });

  it("switching back restores the originals with no request", async () => {
    const root = mount(`<p>Irrigation</p><p>सिंचाई</p>`);
    const translator = make(root, api.fetchTranslations, "en-IN");
    await translator.start();
    // In English, only the Hindi line moved.
    expect(api.calls).toEqual([{ texts: ["सिंचाई"], target: "en-IN" }]);
    const [english, hindi] = root.querySelectorAll("p");
    expect(english.textContent).toBe("Irrigation");
    expect(hindi.textContent).toBe("TRANSLATED(6 chars)");

    await translator.setTarget("hi-IN");
    expect(english.textContent).toBe("हिन्दीअनुवादकिया(Irrigation)");
    expect(hindi.textContent).toBe("सिंचाई");

    const requestsSoFar = api.calls.length;
    await translator.setTarget("en-IN");
    await translator.setTarget("hi-IN");
    expect(api.calls.length).toBe(requestsSoFar);
    expect(english.textContent).toBe("हिन्दीअनुवादकिया(Irrigation)");
    translator.stop();
  });

  it("uses the static dictionary before the network, in both directions", async () => {
    const root = mount(`<a>My farm</a><a>सूचनाएँ</a>`);
    const translator = make(root, api.fetchTranslations, "hi-IN", {
      dictionary: dictionaryLookups(),
    });
    await translator.start();
    expect(root.querySelectorAll("a")[0].textContent).toBe("मेरा खेत");
    await translator.setTarget("en-IN");
    expect(root.querySelectorAll("a")[1].textContent).toBe("Notices");
    expect(api.calls).toHaveLength(0);
    translator.stop();
  });

  it("translates content that appears after load, once", async () => {
    const root = mount(`<ul></ul>`);
    const translator = make(root, api.fetchTranslations);
    await translator.start();
    expect(api.calls).toHaveLength(0);

    const li = document.createElement("li");
    li.textContent = "New notice arrived";
    root.querySelector("ul")!.appendChild(li);
    await settle();
    await translator.whenIdle();

    expect(li.textContent).toBe("हिन्दीअनुवादकिया(New notice arrived)");
    expect(api.calls).toEqual([{ texts: ["New notice arrived"], target: "hi-IN" }]);

    // Our own write is a mutation too; it must not trigger another request.
    await settle();
    await translator.whenIdle();
    expect(api.calls).toHaveLength(1);
    translator.stop();
  });

  it("waits for streamed text to settle before sending it", async () => {
    const root = mount(`<p id="answer"></p>`);
    const translator = make(root, api.fetchTranslations, "hi-IN", { debounceMs: 40 });
    await translator.start();

    const answer = root.querySelector("#answer")!;
    const node = document.createTextNode("");
    answer.appendChild(node);
    for (const partial of ["Irrigate", "Irrigate the", "Irrigate the plot", "Irrigate the plot today"]) {
      node.nodeValue = partial;
      await settle(10);
    }
    await settle(100);
    await translator.whenIdle();

    expect(api.calls).toEqual([{ texts: ["Irrigate the plot today"], target: "hi-IN" }]);
    expect(node.nodeValue).toBe("हिन्दीअनुवादकिया(Irrigate the plot today)");
    translator.stop();
  });

  it("treats a value written by React as the new original", async () => {
    const root = mount(`<p>Pending</p>`);
    const translator = make(root, api.fetchTranslations);
    await translator.start();
    const node = root.querySelector("p")!.firstChild!;
    expect(node.nodeValue).toBe("हिन्दीअनुवादकिया(Pending)");

    node.nodeValue = "Approved";
    await settle();
    await translator.whenIdle();
    expect(node.nodeValue).toBe("हिन्दीअनुवादकिया(Approved)");

    await translator.setTarget("en-IN");
    expect(node.nodeValue).toBe("Approved");
    translator.stop();
  });

  it("leaves source text on screen when the request fails, and retry() tries again", async () => {
    const root = mount(`<p>Soil sample</p>`);
    let fail = true;
    const statuses: { busy: boolean; failed: number }[] = [];
    const fetchTranslations = vi.fn<Fetch>(async (texts) => {
      if (fail) throw new Error("502");
      return texts.map((t) => `हिन्दीअनुवादकिया(${t})`);
    });
    const translator = make(root, fetchTranslations, "hi-IN", {
      onStatus: (s: { busy: boolean; failed: number }) => statuses.push(s),
    });

    await translator.start();
    expect(root.querySelector("p")!.textContent).toBe("Soil sample");
    expect(statuses.at(-1)).toEqual({ busy: false, failed: 1 });

    // A failed string is not re-requested on every mutation.
    root.appendChild(document.createElement("span"));
    await settle();
    await translator.whenIdle();
    expect(fetchTranslations).toHaveBeenCalledTimes(1);

    fail = false;
    await translator.retry();
    expect(root.querySelector("p")!.textContent).toBe("हिन्दीअनुवादकिया(Soil sample)");
    expect(statuses.at(-1)).toEqual({ busy: false, failed: 0 });
    translator.stop();
  });

  it("retries failed strings once on its own, after a pause", async () => {
    const root = mount(`<p>Rate limited</p>`);
    let calls = 0;
    const flaky = vi.fn<Fetch>(async (texts) => {
      calls += 1;
      return texts.map((t) => (calls === 1 ? null : `हिन्दीअनुवादकिया(${t})`));
    });
    const translator = make(root, flaky, "hi-IN", { autoRetryMs: 30 });
    await translator.start();
    expect(root.querySelector("p")!.textContent).toBe("Rate limited");

    await settle(80);
    await translator.whenIdle();
    expect(root.querySelector("p")!.textContent).toBe("हिन्दीअनुवादकिया(Rate limited)");

    // Once only: a string that keeps failing waits for the reader's retry.
    await settle(80);
    expect(flaky).toHaveBeenCalledTimes(2);
    translator.stop();
  });

  it("does not cache what the API could not translate, but does cache what needed none", async () => {
    const root = mount(`<p>Sarvam down</p><p>A</p>`);
    const cache = new TranslationCache(false);
    const api = vi.fn<Fetch>(async (texts) => texts.map((t) => (t === "A" ? "A" : null)));
    const translator = make(root, api, "hi-IN", { cache });
    await translator.start();
    expect(cache.get("hi-IN", "Sarvam down")).toBeUndefined();
    expect(cache.get("hi-IN", "A")).toBe("A");
    translator.stop();
  });

  it("never shows a translation that changed a number, even from cache", async () => {
    const root = mount(`<span>Given 205 bags</span><span>Potato 13.8 kg</span>`);
    const cache = new TranslationCache(false);
    cache.set("hi-IN", "Potato 13.8 kg", "आलू तेरह किलो");
    const api = vi.fn<Fetch>(async (texts) =>
      texts.map((t) => (t === "Given 205 bags" ? "बीस बोरी दी" : "आलू 13.8 किलो")),
    );
    const translator = make(root, api, "hi-IN", { cache });
    await translator.start();
    const [first, second] = root.querySelectorAll("span");
    expect(first.textContent).toBe("Given 205 bags");
    expect(second.textContent).toBe("आलू 13.8 किलो");
    translator.stop();
  });

  it("restarting keeps the originals, so a warm-cache remount can still switch back", async () => {
    // Measured in the browser: React Strict Mode runs the provider effect twice. The first
    // start() applied cached Hindi synchronously; a *second instance* then read that Hindi as
    // the original, and switching to English machine-translated it back ("2.5 t" → "2.5 ct.").
    // One instance, restarted, keeps what it saw first.
    const root = mount(`<p>Given to the collective</p>`);
    const cache = new TranslationCache(false);
    cache.set("hi-IN", "Given to the collective", "समिति को दिया");
    const translator = make(root, api.fetchTranslations, "hi-IN", { cache });

    void translator.start();
    translator.stop();
    await translator.start();

    const p = root.querySelector("p")!;
    expect(p.textContent).toBe("समिति को दिया");
    await translator.setTarget("en-IN");
    expect(p.textContent).toBe("Given to the collective");
    expect(api.calls).toHaveLength(0);
    translator.stop();
  });

  it("a stopped translator does not write when a late response arrives", async () => {
    const root = mount(`<p>Seed</p>`);
    let release: () => void = () => {};
    const slow = vi.fn<Fetch>(
      (texts) =>
        new Promise((resolve) => {
          release = () => resolve(texts.map((t) => `हिन्दीअनुवादकिया(${t})`));
        }),
    );
    const translator = make(root, slow);
    const pending = translator.start();
    translator.stop();
    release();
    await pending;
    expect(root.querySelector("p")!.textContent).toBe("Seed");
  });

  it("does not show a cached translation that is still in the source language", async () => {
    const root = mount(`<p>अनुदान संख्या-11</p>`);
    const cache = new TranslationCache(false);
    cache.set("en-IN", "अनुदान संख्या-11", "In grant संख्या-11");
    const api = vi.fn<Fetch>(async (texts) => texts.map(() => "Grant number-11"));
    const translator = make(root, api, "en-IN", { cache });
    await translator.start();
    expect(root.querySelector("p")!.textContent).toBe("Grant number-11");
    translator.stop();
  });

  it("writes text, never markup, so a hostile translation stays inert", async () => {
    const root = mount(`<p>Hello</p>`);
    const hostile = vi.fn<Fetch>(async (texts) => texts.map(() => `हिन्दीअनुवादकिया<img src=x onerror="alert(1)">`));
    const translator = make(root, hostile);
    await translator.start();
    expect(root.querySelector("img")).toBeNull();
    expect(root.querySelector("p")!.textContent).toBe(`हिन्दीअनुवादकिया<img src=x onerror="alert(1)">`);
    translator.stop();
  });
});

describe("TranslationCache", () => {
  it("starts over when the glossary version changes", () => {
    const cache = new TranslationCache(false);
    cache.useCorpusVersion("a1");
    cache.set("hi-IN", "What has the FPO shared with members?", "समिति ने सदस्यों को क्या बताया है?");
    expect(cache.useCorpusVersion("a1")).toBe(false);
    expect(cache.get("hi-IN", "What has the FPO shared with members?")).toBeDefined();
    expect(cache.useCorpusVersion("b2")).toBe(true);
    expect(cache.get("hi-IN", "What has the FPO shared with members?")).toBeUndefined();
  });

  it("a page served from a stale cache is re-translated once the new version is known", async () => {
    document.body.innerHTML = `<main id="root"><th>Village</th></main>`;
    const root = document.getElementById("root") as HTMLElement;
    const cache = new TranslationCache(false);
    cache.set("hi-IN", "Village", "मोहल्ला");
    const api = vi.fn<Fetch>(async () => ["गाँव"]);
    const translator = new PageTranslator({ root, target: "hi-IN", fetchTranslations: api, cache, debounceMs: 20 });
    await translator.start();
    expect(root.textContent).toBe("मोहल्ला");
    expect(api).not.toHaveBeenCalled();

    expect(cache.useCorpusVersion("new")).toBe(true);
    await translator.refresh();
    expect(root.textContent).toBe("गाँव");
    translator.stop();
    document.body.innerHTML = "";
  });

  it("survives localStorage throwing", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    const cache = new TranslationCache(true);
    cache.set("hi-IN", "Seed", "बीज");
    expect(cache.get("hi-IN", "Seed")).toBe("बीज");
    spy.mockRestore();
  });
});
