# ADR-0023 — Page translation is a DOM layer over Sarvam, with a stored dictionary and a translation memory

Date: 2026-09-16 · Status: Accepted · Amends the language-switch design in commit 1c05625; qualifies ADR-0015 at the display layer only

## Context

Commit 1c05625 gave the farmer portal and the sign-in page a Hindi/English switch backed by a
hand-written table (`lib/i18n.ts`). It translated only what someone had written a Hindi
string for. Everything else stayed in its source language: crop and village names, assistant
answers, the 75 government orders with no `text_en`, and the whole FPO console, which that
commit left English on purpose.

The requirement changed. There should be one switch, top right, on every screen. Pressing it
should put *everything* visible into the other language, including API data and content that
renders after load. Only static chrome should be stored in advance, and the rest should be
translated on demand through Sarvam. We already hold a Sarvam key (ADR-0022).

Constraints that shaped the design:

- The web tier never talks to anything but FastAPI (ADR-0001), and secrets stay in the API's
  environment (NFR-403). The Sarvam key cannot reach the browser.
- Pages are Server Components that render interleaved API data. There is no single string
  table to translate. The rendered DOM is the only place where "everything on the page"
  exists.
- React owns the DOM it renders. Replacing nodes, or translating before hydration, makes
  React either throw hydration errors or quietly write its own text back.
- `make seed && make dev` must still run with no network (NFR-303).

## Decision

**1. Translate the rendered DOM in place, in the browser, after hydration.**
`lib/dom-translate.ts` walks `document.body` and collects text nodes plus `placeholder`,
`aria-label`, `title` and `alt`. It skips `script/style/code/pre/kbd/textarea/svg`,
`[translate="no"]`, `[data-no-translate]` and `.font-mono`, along with text that is only
numbers, URLs, emails, UUIDs, hashes or codes (`FR-812`).

- It writes back only through `Text.nodeValue` and `setAttribute`. There is no `innerHTML`,
  so a hostile translation stays inert text, and no node is replaced, so React keeps its
  references.
- The original of every slot is remembered, so switching back costs no request (NFR-505).
- A `MutationObserver` with a 300 ms quiet period picks up client navigation, streamed
  answers and re-renders. Streamed text is sent once, after it stops changing.
- If React writes a new value, that value becomes the new original.

**2. Source language per string, from the script.** Devanagari is Hindi and Latin is English,
with Devanagari weighted 1.5× so a Hindi sentence that names "AgriVardhak" still reads as
Hindi. Dictionary entries override the heuristic. One mechanism covers both directions and
mixed pages, such as an English console showing a published Hindi order.

**3. Three tiers of resolution:**
- the static dictionary (`lib/strings.json`, synchronous, no network);
- the browser cache (memory + `localStorage`, guarded);
- `POST /api/translate` → FastAPI `POST /api/v1/translate` → the `translation_memory` table →
  Sarvam.

The dictionary is also rendered on the server through `translator(locale)`, so a reload
already shows chrome in the right language. `make i18n-seed` loads the same dictionary into
the translation memory as `HUMAN` rows. A machine write never overwrites a `HUMAN` row.

**4. `translation_memory` is the bilingual corpus.** Each row holds one normalised source
string and one direction: SHA-256 hash, source text, translation, `HUMAN | MACHINE` origin,
provider and model. It grows as the product is used. Nobody writes it in advance.

**5. The model is `mayura:v1`, not the newer `sarvam-translate:v1`. This was measured, not
assumed.** `make translation-eval` runs 29 golden cases. They check what would hurt a reader:
numbers kept, negations kept, legal categories, scheme names, IPM safety wording, and whether
the right crop and pest are named. Results on 2026-09-16:

| Model | Pass | Failures that change meaning |
|---|---|---|
| `sarvam-translate:v1` (2,000-char input) | 24/29 (83%) | "झुलसा रोग … निरीक्षण करें" → *"Inspect the field daily for any sign of **bollworm**"* (the wrong pest, and "daily" was added). "A human approves" → "**एक महिला** … देती है" ("a woman"). "धान की उपज" → "yield of the **crop**". |
| `mayura:v1` (1,000-char input) | 28/29 (97%) | none of the above |

Both models get one case wrong: कृषि रक्षा इकाई (the block's plant protection unit) became
"Agricultural Defense Unit" or "agricultural research unit". The case stays in the eval as a
known failure rather than being loosened.

**6. Spend is bounded.** A signed-in caller has no cap. Anonymous callers (the sign-in page)
share 200 machine translations per hour for each API process, which is enough to translate
the sign-in page once, after which it is served from memory. Each request is capped at 100
texts and 20,000 characters. Every Sarvam failure, a missing key, or `AGRI_USE_FIXTURES=true`
leaves the source text on screen (NFR-304).

**7. What is shown is checked, not trusted.** These rules came out of testing in a real
browser on 2026-09-17, not out of the eval. Each one is enforced in the API and again in the
browser, so a stale cache cannot be looser than the server:

- **Numbers must survive.** On short fragments `mayura:v1` rendered "2.5 t" as "दो सौ पाँच"
  (205), "205 kg" as "बीस किलो" (20 kg) and "13.8 kg" as "तेरह किलो आठ पौंड". A translation
  whose digits differ from the source's is rejected. The string is then retried with only the
  words between the numbers translated and the numbers copied across. If that fails too, the
  source text stays.
- **A number with a bare unit is not translated.** "13.8 t" (tonnes) came back as
  "13.8 किग्रा" (kilograms): the digits were right and the quantity was wrong by 1,000×.
  "13.8 t", "205 kg" and "1.48 ac" stay as written.
- **English output may contain no Devanagari.** Government orders glue words to numbers
  ("संख्या-11", "2401-फसल"), and the model left those words untranslated inside otherwise
  English lines. Hindi output may still contain Latin, because DAP, PM-KISAN and Sarjoo-52 are
  how Hindi prints them.
- **Rate limits.** Sarvam limits the key over a rolling window. One uncached Decision Packet
  page (100+ strings, sent as 3 parallel batches of 5 calls) caused every call in a later
  burst of 15 to return 429. Calls are now capped at 4 in flight across the whole API
  process, with backoff that honours `Retry-After`. The browser sends one batch at a time and
  retries failed strings once, automatically, after 20 s.
- **One translator per document.** React Strict Mode mounts effects twice. With a fresh
  instance per mount, the second instance recorded the first one's cached Hindi as the
  page's *original* text, and switching back to English machine-translated it ("2.5 t" →
  "2.5 ct.").
- The document `<title>` is not translated. In this app it is the product name, and it came
  back as "पौष्टिक" ("nutritious").

**8. Personal names and identifiers are marked `translate="no"`.** That covers farmer and user
names, the organization name, the product name, and `font-mono` identifiers. Crop, village
and block names *are* translated, by explicit request.

**9. Domain terms are fixed by a glossary; the model translates only the prose around them.**
After review, three renderings were wrong in ways that change meaning:

- "FPO CEO" became "महिला आरक्षण आयोग की अध्यक्ष" (chair of the Women's Reservation Commission).
- "the collective", a noun meaning the organisation, became "सामूहिक रूप से" (collectively),
  so "Runs the collective" read as "runs collectively".
- "ac" became "ए.सी." (the letters A.C.), and "1.48 ac" stayed in English.

`agrivardhak/translation/glossary.json` is the lexical corpus. Each term has one Hindi and
one English rendering, used in both directions: FPO ⇄ किसान उत्पादक संगठन, "the collective" →
संगठन, ac/acre/acres ⇄ एकड़, t/ha/q/kg, the crops, MSP, mandi, Kharif/Rabi, and the farmer
table's administrative words. "Village" had become मोहल्ला (a neighbourhood) and should be
गाँव. "Block" should be विकास खंड. "Tract" had become लेख (an article) and should be क्षेत्र.
The three tracts are fixed as दोआब, गंगा-पार and यमुना-पार ("Doab" had become दोहा, Doha).

- **Only terms and numbers** ("FPO", "1.48 ac", "Paddy 1,832 ac"): resolved locally, with no
  API call.
- **Anything else:** terms are replaced by `[T1]`, `[T2]` placeholders before Sarvam sees the
  text, and the canonical words are put back afterwards. Measured: bracket placeholders survive
  and the model inflects around them ("[T2] ने इसे अनुमोदित किया"). `XT1X` got transliterated
  and `{{T1}}` changed the verb. The article stays outside the placeholder: "Runs the [T1]" →
  "[T1] को चलाता है", but "Runs [T1]" → "दौड़ [T1]" (run, on foot).
- **A number and its unit share one placeholder.** "on 857 [T3]" came back as
  "857 सरसों पर [T3]", with the number separated from its unit. With one placeholder,
  "on [T3]" → "[T3] पर", where [T3] = "857 एकड़".
- **A dropped placeholder** (measured: `[T3]` vanished once) means only the prose between the
  terms is translated.
- **Every result is checked,** whether fresh or from memory. Each term must appear in its
  canonical form, at least as often as in the source. A machine row whose source contains a
  term is served only if it was produced under the current glossary version
  (`translation_memory.corpus_version`). "Runs the collective. Sees the whole organization."
  had been stored as "सामूहिक रूप से चलता है। पूरे संगठन को…" and passed a presence check,
  because संगठन was there as the translation of "organization".
- **The hand-written dictionary has to agree with the glossary.** A test fails if it doesn't:
  it had FPO as समिति and एफ़पीओ. The browser clears its cache when the API reports a new
  glossary version.

Not in the glossary: ordinary vocabulary. Keeping it small is what keeps it maintainable. Add a
term when a translation changes a domain word's meaning, and record why in its `why` field.

## Consequences

- Every screen, including the FPO console, can be read in either language, and new screens
  need no translation work.
- **Machine-translated government orders are shown unlabelled.** This was asked for explicitly
  and it is a real trade-off. ADR-0015 still holds for *storage*: `KnowledgeChunk.text_hi`
  remains the canonical order, nothing downstream reads a rule from `translation_memory`, and
  the eval pins लघु एवं सीमांत कृषक → "small and marginal". But in English, a farmer reading a
  notice with no publisher English is reading a machine rendering of a legal document, and
  nothing on screen says so. The `notices.originalHindi` label that used to say so is gone.
- **Page text goes to Sarvam as a third-party processor.** That includes crop, village and
  block names and assistant answers about a farmer's own plots. Personal names are excluded
  by `translate="no"`. INV-9 consent for this processing purpose is not modelled yet, and it
  must be before this reaches real farmers.
- Translation happens fragment by fragment. `Crop health <strong>82%</strong>` is translated as
  separate text nodes, so word order across an inline element cannot be rearranged. That is
  the cost of never touching structure.
- The first visit to a screen that has never been translated shows its source text until the
  batches complete. For a large Decision Packet page that is 10–20 s. After that the
  translation memory serves the page immediately. Short fragments can still come back
  partly translated ("ओवरड्यू since 12 सितंबर"), because the rules above protect numbers and
  script, not fluency. Chrome is already in Hindi from the server render.
- Village names are still transliterated by the model, and inconsistently: Meja appears as
  both मेजा and मीजा, Chaka as चका and चक़ा. They are proper nouns and are not in the glossary.
  The options are to mark them `translate="no"` or to add a transliteration table from the
  seed.
- Placeholders keep terms exact but cannot fix word order. "What are the biggest risks facing
  our FPO this month?" came back with the organisation misplaced in the sentence: the term
  itself is correct, the grammar around it is the model's.
- The router model (ADR-0020) and the translation model are both perishable. Re-run
  `make translation-eval` before changing `AGRI_SARVAM_TRANSLATE_MODEL`.

## Alternatives considered

- **Keep hand-writing every string in `i18n.ts`.** Rejected. It cannot translate API data and
  it does not scale to the console, which is what the requirement is about.
- **Translate on the server before rendering** (a `t()` that calls the API). Rejected. Every
  interpolated API value would need wrapping at every call site, client components and
  streamed answers would still need a browser path, and each server render would block on a
  provider call.
- **Replace `innerHTML` with a translated HTML fragment.** Rejected. It is an injection
  surface, it breaks React's references, and machine translation does not reliably preserve
  markup.
- **Browser-only machine translation (Chrome's built-in translator).** Rejected. It is not
  controllable, not cacheable into a corpus we own, not measurable, and not available on
  every farmer's phone browser.
- **`sarvam-translate:v1` as default.** It is newer, has a 2× input limit and scores better
  chrF against our dictionary (66.7 vs 55.9). It was rejected on the eval above, because
  its errors change meaning while mayura's lower chrF comes from wording choices on short
  labels, which the static dictionary already covers.
