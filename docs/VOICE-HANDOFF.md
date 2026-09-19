# Voice Assistant — Implementation Handoff

Date: 2026-09-17 · Status: **designed, nothing built** · Design:
[`docs/superpowers/specs/2026-09-17-voice-assistant-design.md`](superpowers/specs/2026-09-17-voice-assistant-design.md)

This is the ordered task list for building the conversational voice channel. **Read the spec
first.** Decisions D1–D26 are settled; do not re-ask them. When this file says "§N", it means
that section of the spec. Paths are repo-relative.

---

## 0. Before you start

### 0.1 Branch
Voice depends on the Sarvam client, the translation service and the glossary, which live on
`feat/dual-language-inclusion` (commits `76382c7`, `2bb798c`) and may not be on `main` yet.

```bash
git fetch origin
# if feat/dual-language-inclusion is merged into main:
git checkout -b feat/voice-assistant origin/main
# otherwise:
git checkout -b feat/voice-assistant origin/feat/dual-language-inclusion
```
Check that `apps/api/agrivardhak/translation/sarvam.py` and `translation/glossary.json` exist. If
not, you are on the wrong base.

### 0.2 Prerequisites
- `.env` has `AGRI_SARVAM_API_KEY` (the same key serves chat, translate, STT and TTS).
- `AGRI_LLM_PROVIDER=sarvam`.
- `make setup && make upgrade && make seed` succeed; `make test` is green **before** you change anything.
- Read: `CLAUDE.md`, `context.md`, `docs/adr/0008-graded-channel-depth.md`,
  `docs/adr/0022-*.md`, `docs/adr/0023-*.md`.

### 0.3 Code you will reuse (do not rewrite)
| Need | Existing code |
|---|---|
| Answer a question | `apps/api/agrivardhak/orchestrator/chat.py:answer(session, *, scope, request, as_of=None, plan=None) -> AssistantAnswer` |
| Request/answer shapes | `orchestrator/assistant_contracts.py`: `AssistantRequest` (question ≤500 chars, `conversation_id`, `anchor_packet_id`), `AssistantAnswer`, `IntentPlan` (`router_confidence`), `ResponseShape`, `LookupKey` |
| Packet + claims | `orchestrator/packet.py`: `Claim` (`statement, magnitude, unit, confidence, evidence`), `ConfidenceBlock` (`overall, below_floor, what_would_raise_it`), `DecisionPacket`, `SECTION_ORDER` |
| Refusal text | `orchestrator/chat.py:46-56` `FARMER_REFUSAL` / `STAFF_REFUSAL`; `_unknown_crop` `:120` |
| Router | `orchestrator/router.py:plan(question, audience, anchor_packet_id)`; `_shapes_for` `:115`; `_CROP_TEXT` `:229`; `_fallback` `:382`; `_FARMER_HINTS` `:374` |
| LLM JSON call | `orchestrator/llm.py:structured(*, system, user, schema, schema_name) -> dict \| None` (never raises) |
| Number extraction | `translation/quality.py:numbers`; `translation/service.py:numbers_kept` `:176` |
| Script detection | `translation/service.py:detect(text) -> "hi-IN" \| "en-IN" \| None` |
| Glossary | `translation/glossary.py:load()`, `Glossary`, `Term`; data in `translation/glossary.json` |
| Sarvam HTTP style (retries, never-raise, concurrency cap) | `translation/sarvam.py` (`_call`, `_retry_delay`, semaphore at `:45`) |
| Auth | `api/auth.py:issue_token(...)`, `current_scope`; JWT settings `config.py:23-25` |
| Scope | `api/scope.py:ContextScope` (`audience`, `is_farmer`, `is_org_staff`), `ScopeViolation` |
| Chat guard semantics | `api/chat.py:_guard` `:62` |
| Turn recording | `orchestrator/chat.py:_record` `:271`; model `domain/models/operations.py:ConversationTurn` `:221` |
| Router mounting | `api/main.py:113-119` (`app.include_router(...)`) |
| Next.js proxy pattern | `apps/web/src/app/api/assistant/chat/route.ts` (`sessionToken()` from `@/lib/session`) |
| Web chat (text fallback target) | `apps/web/src/components/chat.tsx` `ChatPanel`; claim/section rendering in `components/packet.tsx` |
| Farmer / staff ask pages | `apps/web/src/app/(farmer)/ask/page.tsx`, `apps/web/src/app/(fpo)/assistant/page.tsx` |
| i18n | `apps/web/src/lib/strings.json` + `make i18n-seed` |
| Progress evidence | `scripts/progress.py` `Deliverable` / `Evidence`; M34 at `:342` is the model to copy |
| Test fixtures | `apps/api/tests/conftest.py` (`session`, `staff_user`, …) |

> **Contracts note:** CLAUDE.md mentions `packages/contracts`, but that package **does not exist**.
> Web payload types are hand-written (`apps/web/src/lib/api.ts`). Put voice types in
> `apps/web/src/lib/voice-contracts.ts` with a header comment naming
> `apps/api/agrivardhak/voice/contracts.py` as the source of truth.

---

## Task 0 — Spike: verify Sarvam speech APIs (throwaway, ≤1 h)

Why: §2.3 lists facts that are **unverified**. Nothing below should be built on guesses.

1. Read the live docs: Sarvam STT REST + streaming WS, TTS REST + streaming WS.
2. Write a throwaway script in the session scratchpad (not the repo) that:
   - sends 5 short 16 kHz WAV clips to STT REST with `model=saaras:v3`, trying `mode=transcribe`
     and `mode=codemix` (record Hindi/Hinglish yourself or synthesise them with Bulbul): "aaj kya karna hai",
     "mere gehun ki paidavar kitni hogi", "haan", "kyon", "yojana ke baare mein batao";
   - opens the STT streaming WS once and records partial/final event shapes, endpointing signals,
     whether it returns `language_code` and a confidence;
   - calls TTS REST + WS with `bulbul:v3`, Hindi text containing "₹2150 प्रति क्विंटल" and "3.8 टन",
     and records how digits are spoken, the parameter names for speaker/pace, and the codec and sample-rate options;
   - measures latency (request → first byte) for each.
3. Decide: (a) does Bulbul speak Indian-grouped digits correctly? (if yes, `spoken_numbers` is unit
   expansion only, §6.5); (b) English pivot for routing: STT `translate` mode vs
   `translation.service.translate`, whichever is faster with acceptable quality.
4. Record URLs, headers, parameter names, event shapes, latencies and both decisions in ADR-0024 (Task 1).

**Acceptance:** ADR-0024 has a "Measured on 2026-09-xx" table. No spike code is committed.

---

## Task 1 — Evidence row, ADR, requirements (docs first, CLAUDE.md §8)

### 1.1 `scripts/progress.py`
Add after M34, modelled on it:
```python
Deliverable("V1", "Conversational voice channel (farmer + read-only staff)", "7",
            "UI-06, FR-822, FR-823, FR-824, FR-825, FR-826, FR-827, FR-828, ADR-0024",
            Evidence(symbols=["agrivardhak.voice.composer:compose",
                              "agrivardhak.voice.disclosure:plan_disclosure",
                              "agrivardhak.voice.guard:check",
                              "agrivardhak.voice.session:VoiceSession",
                              "agrivardhak.api.voice:router",
                              "agrivardhak.domain.models:VoiceTurn"],
                     files=["docs/adr/0024-conversational-voice-channel.md",
                            "apps/api/agrivardhak/voice/prompts/spoken_turn.md",
                            "apps/web/src/components/voice/use-voice-session.ts"],
                     tests=["test_voice_turn_is_at_most_three_sentences",
                            "test_voice_haan_advances_without_routing",
                            "test_voice_staff_cannot_approve_by_voice",
                            "test_voice_scope_comes_only_from_ticket",
                            "test_voice_extension_seam_farmer_decision",
                            "test_devanagari_tasks_today_routes_without_llm"])),
```
Use the phase label the file uses for the current phase (check the neighbours; "7" is a placeholder).
Run `make progress`. V1 should show as not built.

### 1.2 `docs/adr/0024-conversational-voice-channel.md`
Use the existing ADR template (copy the headings from `0023`). Content:
- **Context:** ADR-0008 demo-grade voice; farmers' literacy; the Ask output is structured.
- **Decision:** cascaded Sarvam Saaras v3 → orchestrator → composer (LLM + guard + template) → Bulbul
  v3 over a browser WebSocket. Progressive disclosure. Read-only staff voice. Transcripts only.
  Single-worker session registry (~20 sessions). Telephony POST-MVP.
- **Measured:** the Task 0 table.
- **Consequences:** supersedes the voice row of ADR-0008; the multi-worker limit; no feature phones yet.
- **Alternatives:** speech-to-speech models; browser Web Speech primary; Exotel now; HTTP per turn.
Link it from `context.md` (the decision log and T-05 at `:202`).

### 1.3 `docs/SRS.md`
- UI-06 (`:170`): priority → MUST. Text: "The farmer portal and FPO assistant SHALL offer a
  conversational voice mode (Hindi, English, Hinglish) with streaming speech recognition, spoken
  answers and barge-in."
- Append after FR-821 (IDs are stable; do not renumber):

| ID | Requirement | Priority |
|---|---|---|
| FR-822 | A spoken assistant turn SHALL contain at most three sentences and at most one follow-up question; remaining content SHALL be disclosed only on request. | MUST |
| FR-823 | Every number spoken by the voice assistant SHALL resolve to a magnitude of an evidenced claim in the answer being spoken; a model-composed turn that fails this check SHALL be replaced by a deterministic template (extends FR-817). | MUST |
| FR-824 | Voice disclosure MAY defer packet sections but SHALL NOT remove them; every deferred section SHALL remain reachable on screen in the same conversation (reconciles FR-818). | MUST |
| FR-825 | No consequential action (approval, rejection, execution) SHALL be accepted by voice; the assistant SHALL direct the user to the screen (INV-1). | MUST |
| FR-826 | The voice channel SHALL NOT persist audio; transcripts and spoken text SHALL be recorded as assistant turns (INV-9, FR-820). | MUST |
| FR-827 | On speech-service failure or sustained latency the voice channel SHALL degrade in order: template wording, browser speech synthesis, text chat, without losing the conversation. | MUST |
| FR-828 | The commands stop, repeat, show on screen and talk to a person SHALL be available at any point in a voice conversation. | SHOULD |

- Acceptance scenario 8 (`:547`): "A farmer opens the portal in Hindi, taps the mic, asks 'aaj kya
  karna hai?', hears at most three sentences and one follow-up, says 'haan' and hears the next
  item, all scoped to their own farm. (UI-05, UI-06, FR-808, FR-822)".
- Traceability table (§9.2): add FR-825 → INV-1, FR-823 → INV-3, FR-826 → INV-9.

### 1.4 Other docs
- `docs/MVP-SCOPE.md`: rewrite the voice row at `:29` to point at ADR-0024; fix demo step 10 at
  `:219` (voice is no longer descoped); keep "Telephony IVR | POST-MVP" at `:98`.
- `docs/ARCHITECTURE.md:465-467`: the endpoint is `/api/v1/assistant/chat` (text) and
  `/api/v1/voice/ws` (voice). Add a short "Voice layer" section with the §4 diagram.
- `docs/GLOSSARY.md`: `VoiceSession`, `SpokenTurn`, `DisclosureQueue`, `AudiencePolicy`, `VoiceTurn`.
- `CLAUDE.md` stack table, Voice row: "Sarvam Saaras v3 STT + Bulbul v3 TTS over WebSocket;
  browser speechSynthesis fallback (ADR-0024)".

**Acceptance:** `make progress` runs; docs build-free check: `grep -n "FR-828" docs/SRS.md`.

---

## Task 2 — Pure core (TDD, no I/O)

Create `apps/api/agrivardhak/voice/{__init__,contracts,spoken_numbers,guard,templates,disclosure,followup,commands,degrade}.py`,
`voice/lexicon.json`, and `voice/audience/{__init__,farmer}.py`. Contract shapes are in spec §5.
Add `agrivardhak.voice.*` to the strict mypy overrides in `apps/api/pyproject.toml`.

Write each test **first**, watch it fail, then implement. Tests go in
`apps/api/tests/test_voice_core.py` (no DB fixtures needed).

| Module | Tests to write first |
|---|---|
| `contracts` | `test_voice_spoken_turn_is_frozen`, `test_voice_policy_shapes_are_frozenset` |
| `spoken_numbers` | `test_voice_paise_to_rupee_words_hi` (215000 paise → "do hazaar ek sau pachaas rupaye"), `test_voice_lakh_grouping_hi`, `test_voice_decimal_hi`, `test_voice_english_passthrough`. Skip digit wording if Task 0 found that Bulbul handles it; keep unit expansion tests. |
| `guard` | `test_voice_turn_is_at_most_three_sentences`, `test_voice_rejects_number_not_in_claims`, `test_voice_accepts_paise_to_rupee_conversion`, `test_voice_rejects_two_questions`, `test_voice_rejects_markdown_and_urls`, `test_voice_crop_protection_requires_label_wording`, `test_voice_crop_protection_rejects_dosage`, `test_voice_rejects_other_farmer_name_for_farmer_audience`, `test_voice_rejects_wrong_script` |
| `templates` | `test_voice_template_exists_for_every_farmer_lookup_in_both_languages` (iterate `LookupKey` farmer keys × `SpokenLanguage`), `test_voice_every_template_passes_guard` (render with sample claims → `guard.check` is True) |
| `followup` | `test_voice_followup_matches_haan_variants` ("haan", "हाँ", "ha ji", "yes", "theek hai"), `test_voice_followup_matches_kyon_kab_aur`, `test_voice_followup_none_for_new_question` ("sarson ka bhav kya hai" → None) |
| `commands` | `test_voice_command_ruko_bas_stop`, `test_voice_command_phir_se_bolo`, `test_voice_command_screen_par_dikhao`, `test_voice_command_insaan_se_baat`, `test_voice_command_not_triggered_inside_question` ("ruko mat, batao" handled as stop only if the leading token matches, documented) |
| `disclosure` | `test_voice_lookup_chunks_two_claims_max`, `test_voice_lookup_more_than_six_claims_ends_in_screen_only`, `test_voice_refusal_is_single_terminal_chunk`, `test_voice_low_confidence_claim_offers_why`, `test_voice_decision_order_bottom_line_first` (with a staff-like stub policy: head = recommendation[0]; WHY → situation+impact; WHEN → schedule), `test_voice_decision_speaks_at_most_three_recommendations`, `test_voice_screen_only_sections_never_spoken` |
| `degrade` | one test per row of spec §8, e.g. `test_voice_two_slow_turns_degrade_to_text`, `test_voice_single_slow_turn_does_not_degrade`, `test_voice_two_stt_failures_degrade_to_text`, `test_voice_tts_failure_emits_browser_fallback` |
| `audience` | `test_voice_extension_seam_farmer_decision`: build a stub farmer policy with DECISION allowed, feed a sample `AssistantAnswer(shape=DECISION)` through `plan_disclosure` + template compose, and assert a valid turn. No edits to core modules are allowed to make this pass. |

Rules: no imports from `sqlalchemy`, `httpx`, `datetime.now` in these modules. Use sample
`Claim`/`DecisionPacket` objects built in a local test helper (look at `tests/test_assistant_chat.py`
for existing builders before writing new ones).

**Acceptance:** `cd apps/api && .venv/bin/python -m pytest -q tests/test_voice_core.py` green;
`make check` green.

---

## Task 3 — Composer (LLM → guard → template)

Files: `voice/composer.py`, `voice/prompts/spoken_turn.md`, a small change to `orchestrator/llm.py`.

1. `llm.structured(...)`: add keyword `timeout_seconds: float | None = None`, defaulting to
   `settings.router_timeout_seconds`. Existing callers are unchanged.
   Test: `test_structured_honours_timeout_override` (monkeypatch httpx client and assert the timeout passed).
2. `prompts/spoken_turn.md` (versioned header `version: spoken-turn-v1`). Must state:
   - persona Vardhak, *aap*, simple rural words, the language rule (D25);
   - use ONLY the provided claims; write numbers as digits; never invent numbers;
   - ≤3 sentences; exactly one short follow-up question matching the given `offer` intent, or none;
   - mandatory glossary terms (list injected);
   - crop-protection rule (INV-8 wording);
   - no lists, markdown or English jargon in Hindi output;
   - output JSON `{say, offer}`.
   Load it with a small loader that reads the file once and exposes `SPOKEN_PROMPT_VERSION`.
3. `compose(chunk, *, language, slots, policy, llm_timeout) -> SpokenTurn`, per spec §6.3,
   including the implicit-confirm prefix and returning `source`.

Tests (`tests/test_voice_composer.py`, monkeypatch `llm.structured`):
`test_voice_composer_uses_llm_when_guard_passes`, `test_voice_composer_falls_back_on_guard_failure`
(LLM returns an invented number), `test_voice_composer_falls_back_on_none` (timeout),
`test_voice_composer_template_when_llm_unavailable` (FR-821),
`test_voice_composer_refusal_never_calls_llm`, `test_voice_composer_adds_implicit_confirm_prefix`.

**Acceptance:** tests green. Live check (optional, needs key): a script in the scratchpad composes 5
seeded chunks; eyeball the Hindi.

---

## Task 4 — Router understands Hindi without the model (D16)

Files: `orchestrator/router.py`, `api/chat.py`, `voice/speech/pivot.py`.

1. `router.plan(..., question_pivot_en: str | None = None)`: when present, `_user_prompt` includes
   both "Question (as spoken)" and "English rendering". The keyword `_fallback` checks both texts.
2. Extend `_FARMER_HINTS` with Devanagari and Hinglish keywords. Derive crop names from
   `translation/glossary.json` at import; hand-add intent phrases (आज क्या करना / aaj kya karna → tasks;
   पैदावार / paidavar / upaj → yield gap; योजना / yojana → schemes; सूचना / ghoshna → announcements;
   मेरा खेत / mera khet → profile).
3. `_CROP_TEXT` (`:229`) accepts Devanagari letters. `_known_crop` maps Hindi crop names through the
   glossary.
4. `voice/speech/pivot.py:to_english(session, text) -> str | None`: the mechanism chosen in Task 0.
5. `api/chat.py`: when `translation.service.detect(question) == "hi-IN"`, compute the pivot and pass it
   (typed Hindi benefits too).

Tests (`tests/test_assistant_chat.py` or a new `tests/test_router_hindi.py`, LLM disabled via
`AGRI_LLM_PROVIDER=none` / settings override):
`test_devanagari_tasks_today_routes_without_llm` ("आज क्या करना है" → LOOKUP `MY_TASKS_TODAY`),
`test_hinglish_yield_routes_without_llm` ("mere gehun ki paidavar"), `test_devanagari_crop_is_known`
("सरसों"), `test_pivot_is_passed_to_router_prompt`.
Run `make routing-eval` afterwards if a key is available and note any accuracy change in ADR-0024.

**Acceptance:** new tests green; existing router tests unchanged and green.

---

## Task 5 — Speech adapters

Files: `voice/speech/{stt,tts,sarvam_stt,sarvam_tts,fixtures}.py`, `config.py`, `.env.example`.

- `stt.py`: `class SpeechToText(Protocol)`: `async def stream(self, frames: AsyncIterator[bytes], language_hint) -> AsyncIterator[Transcript]`
  and `async def transcribe_clip(self, wav: bytes, language_hint) -> Transcript | None`.
- `tts.py`: `class TextToSpeech(Protocol)`: `async def synthesize(self, text, language, pace, speaker) -> AsyncIterator[bytes]`.
- Sarvam implementations use the Task 0 facts. Style follows `translation/sarvam.py`: bounded concurrency
  (`asyncio.Semaphore(voice_max_sessions)`), retry once on 429/5xx, **never raise to the caller**
  (return None / end the iterator and log). Use `websockets` or `httpx` (check `pyproject.toml` first;
  add a dependency via `uv add` only if needed, and name it in ADR-0024).
- `fixtures.py`: `FixtureSTT` maps known WAV hashes or text-prompt bytes to transcripts (tests send
  UTF-8 text frames as "audio"); `FixtureTTS` yields `b"FAKE-AUDIO:" + text`. Selected when
  `settings.use_fixtures` is true or in tests.
- `config.py` fields: spec §12 list. Mirror them in `.env.example` with comments.

Tests (`tests/test_voice_speech.py`): `test_voice_fixture_stt_roundtrip`,
`test_voice_sarvam_stt_returns_none_on_5xx` (monkeypatched transport), `test_voice_sarvam_tts_never_raises`.
A live test is marked `@pytest.mark.live` and skipped without the key.

---

## Task 6 — Session, persistence, transport, API

### 6.1 Migrations (`make migrate m="voice turns and helpline"`, then review the autogenerated file)
- `conversation_turn.channel` (`VARCHAR(8) NOT NULL server_default 'text'`).
- New model `VoiceTurn` in `domain/models/operations.py` next to `ConversationTurn`, exported from
  `domain/models/__init__.py`. Columns per spec §12. Append-only, so no `updated_at` (CLAUDE.md §6). UUIDv7 id.
- `organization.helpline_phone VARCHAR(20) NULL`.
- Seed: set `helpline_phone` for the demo FPO in `seed/generator.py:330` with a clearly synthetic
  number, commented `SYNTHETIC — DEMO ONLY`.
- `orchestrator/chat.py:answer(..., channel: str = "text")` → `_record(..., channel=channel)`.

### 6.2 `voice/session.py`
Implement spec §7 exactly: states, resolution order, slot prefill (via the farmer profile lookup in
`orchestrator/lookups/farmer.py`), language-switch question (D21), silence timers (D24, driven by
`playback_done` events and `asyncio` tasks, with the clock injected for tests), filler (D10), the degrade
ladder via `degrade.py`, and a `VoiceTurn` write for every spoken turn. DB work runs in a thread
(`anyio.to_thread.run_sync`) with a fresh `Session` per turn, because `chat.answer` is sync.
Registry: an in-process dict + lock + a sweeper task started from a FastAPI lifespan in `api/main.py` (none exists yet — add one).
Enforce `voice_max_sessions`; beyond it return error `busy` → web shows text chat.

`voice/audience/staff.py` (ISOLATED, D7): `POLICY` with `allowed_shapes={LOOKUP, DECISION,
EXPLAIN, REFUSE}` (mirror what the router allows staff), `decision_order` per spec §6.2,
`screen_only_sections={"evidence", "drilldown", "overrides", "actions"}`,
`forbidden_utterance_patterns` (approve/manzoor/sweekar/execute/lagu karo/reject/asweekar …).
**Commit staff work separately** as `feat(voice): staff read-only voice`.

### 6.3 `api/voice.py` + `voice/transport/browser_ws.py`
- `POST /api/v1/voice/ticket` (depends on `current_scope`, applies `_guard` semantics) → issues a JWT
  with the same claims as `issue_token` plus `purpose: "voice"`, `exp = now + voice_ticket_ttl_seconds`.
  Returns `{ticket, ws_url}`. If there is no policy for the audience, return 403.
- `WS /api/v1/voice/ws?ticket=…`: decode, require `purpose == "voice"`, build `ContextScope` exactly as
  `current_scope` does (factor the claims → scope code into a helper in `api/auth.py`, don't duplicate it).
  **Never read org_id/farmer_id from client messages.**
- Farmer policy is registered in `voice/audience/__init__.py`; staff by one line in `api/voice.py`:
  `register_policy(staff.POLICY)`.
- Mount: `app.include_router(voice.router)` in `api/main.py`.

Tests (`tests/test_voice_session.py`, using FastAPI `TestClient.websocket_connect`, fixture STT/TTS,
monkeypatched `router.plan` / `llm.structured`):
- `test_voice_greeting_uses_farmer_name`
- `test_voice_haan_advances_without_routing` (spy on `router.plan`, called once)
- `test_voice_phir_se_bolo_replays_without_llm`
- `test_voice_kyon_on_packet_uses_frozen_packet` (EXPLAIN path, no `engine.ask`)
- `test_voice_low_router_confidence_asks_explicit_confirm`
- `test_voice_language_switch_asked_once`
- `test_voice_silence_nudge_then_close` (injected clock)
- `test_voice_two_slow_turns_send_degrade_to_text`
- `test_voice_every_spoken_turn_writes_voice_turn_row`
- `test_voice_insaan_se_baat_returns_helpline`
- `test_voice_session_limit_returns_busy`

Invariant tests, **added to `tests/test_invariants.py`**:
- `test_voice_staff_cannot_approve_by_voice`: a staff session says "isko approve karo" → forbidden
  template; no `Approval` rows; no recommendation state change.
- `test_voice_scope_comes_only_from_ticket`: the client sends `{"farmer_id": other}` in a frame → ignored;
  lookups still use the ticket farmer.
- `test_voice_no_audio_persisted`: after a session, no table has a bytea/large binary value from the
  session (assert on `voice_turn` columns + a schema check that no voice-related column is binary).
- `test_voice_ticket_rejects_normal_session_jwt` (a regular token without `purpose=voice` is refused on WS).

**Acceptance:** all green; `make upgrade && make seed` work on a fresh DB.

---

## Task 7 — Web voice UI

Files under `apps/web/src/`:
```
app/api/voice/ticket/route.ts           POST → FastAPI /api/v1/voice/ticket (copy chat/route.ts auth pattern)
lib/voice-contracts.ts                  TS mirror of spec §5 events
components/voice/use-voice-session.ts   hook: ticket → WS, AudioWorklet capture, VAD, playback, barge-in
components/voice/pcm-worklet.js         AudioWorkletProcessor: downsample to 16 kHz PCM16, 20 ms frames (in public/ if the bundler requires)
components/voice/voice-view.tsx         "use client" container: orb + captions + card + chips + hold-to-talk
components/voice/voice-orb.tsx          states: listening / thinking / speaking / idle
components/voice/captions.tsx           both sides, digits kept
components/voice/spoken-card.tsx        reuse claim/section renderers from components/packet.tsx + confidence chip
components/voice/offer-chips.tsx        Haan / Nahi / Kyon / Kab / Aur batao → tap_offer
components/voice/hold-to-talk.tsx       pointerdown start / pointerup end_of_speech
components/voice/speech-fallback.ts     window.speechSynthesis, lang hi-IN/en-IN, rate from pace
components/voice/staff-voice-entry.tsx  ISOLATED staff mic button (D7)
components/voice/__tests__/*.test.ts(x) vitest
```
Behaviour:
- Farmer `/ask`: a big mic button above `ChatPanel` opens `VoiceView`. On `degrade{to_text}` or
  `busy`, close voice, show the message, and keep `ChatPanel` with the **same conversation_id** (lift the
  id out of `ChatPanel` into the page or pass a prop; `chat.tsx:97-101` currently creates it).
- Mic permission: request on the tap (a user gesture). On denial, show a text explanation + chips.
- `getUserMedia({audio: {echoCancellation: true, noiseSuppression: true, autoGainControl: true}})`.
- Barge-in: while playing, if client VAD energy > threshold for ≥200 ms → stop playback immediately,
  send `barge_in`.
- `show_screen` → render the full answer (the packet via `PacketView` or claims) below the orb.
- HUMAN handoff card: number + `tel:` link.
- All strings through i18n (`strings.json`, then `make i18n-seed`).
- Staff: `(fpo)/assistant/page.tsx` imports `staff-voice-entry.tsx` (one import + one element; its own commit).

Vitest: `voice-view renders offer chips from a turn event`, `degrade event switches to chat with
same conversation id`, `tts_fallback calls speechSynthesis`, `barge_in stops playback`.

**Acceptance:** `make check`, `make test-web` green; the manual demo in §Verification works in Chrome.

---

## Task 8 — Close out

1. `make check && make test && make progress` → V1 fully evidenced; `make progress-check` passes.
2. Update `PROGRESS.md` via `make progress` only (never by hand).
3. Rehearse the demo below twice; paste the latency observations into ADR-0024.
4. Commit in logical commits (docs, core, composer, router, speech, session/API, web farmer, **staff
   voice separately**), each ending with the repo's attribution line. Open a PR against the base
   branch you cut from.

---

## Verification checklist

- [ ] `tests/test_voice_core.py`, `test_voice_composer.py`, `test_voice_speech.py`,
      `test_voice_session.py`, `test_router_hindi.py` green
- [ ] 4 new voice invariant tests in `test_invariants.py` green
- [ ] `make check` (ruff, mypy strict incl. `voice/`, tsc, eslint) green
- [ ] `make test` green with **no network** (`AGRI_USE_FIXTURES=1`)
- [ ] `make progress-check` passes; V1 evidenced
- [ ] Docs updated: ADR-0024, SRS (UI-06, FR-822–828, scenario 8), MVP-SCOPE, ARCHITECTURE, GLOSSARY,
      context.md, CLAUDE.md stack row
- [ ] Staff voice is a separate commit and reverting it leaves farmer voice working (try
      `git revert --no-commit <sha> && make test` then `git revert --abort`)

## Demo script (manual, Chrome, `make seed && make dev`)

1. Sign in as the seeded **farmer**. Open `/ask` and tap the mic.
   Hear: "Namaste {naam} ji, main Vardhak hoon. Aap kya poochna chahenge?"
2. Say **"aaj kya karna hai?"** → hear ≤3 sentences starting with an implicit confirmation, plus one
   offer ("Aur batau?"). The card shows the task with its confidence chip.
3. Say **"haan"** → the next item (no routing delay).
4. Say **"kyon?"** on a low-confidence item → hear what would raise confidence.
5. Start talking while it speaks → it stops (barge-in). Say **"ruko"** → silence, still listening.
6. Say **"phir se bolo"** → the last turn repeats.
7. Say **"insaan se baat karni hai"** → hear and see the FPO helpline with tap-to-call.
8. Stay silent → nudge at ~8 s, closing line at ~20 s, mic closes.
9. Sign in as the **FPO CEO**. On `/assistant`, tap the mic and say **"is season mein kya karna chahiye?"**
   → explicit confirm → headline recommendation + expected outcome + confidence word → "kyon" →
   situation/impact → say **"approve karo"** → "Approve karne ke liye screen par dekhein." and the
   packet appears on screen.
10. Unset `AGRI_SARVAM_API_KEY` and restart the API → voice still answers through templates + browser
    speech; with STT unavailable it switches to text and keeps the conversation.
