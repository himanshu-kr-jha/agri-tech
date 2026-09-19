# Conversational Voice Assistant ("Vardhak") — Design Spec

Date: 2026-09-17 · Status: **approved design, not built** · Branch to build on:
`feat/voice-assistant` (cut from `feat/dual-language-inclusion`) · ADR to write: **ADR-0024**
Companion task list: [`docs/VOICE-HANDOFF.md`](../../VOICE-HANDOFF.md)

This document is the *what and why*. The handoff is the *how, in order*. Every decision below was
settled in a product grilling session. An implementer should not re-open them without
talking to the product owner.

---

## 1. Context

Farmers served by the FPO have low text literacy (`context.md:226`). The Ask feature today is text:

```
apps/web/src/components/chat.tsx  (ChatPanel)
  → apps/web/src/app/api/assistant/chat/route.ts   (SSE proxy)
  → POST /api/v1/assistant/chat/stream             (apps/api/agrivardhak/api/chat.py)
  → orchestrator/chat.py:answer(session, scope=, request=) -> AssistantAnswer
       router.plan → REFUSE | EXPLAIN | LOOKUP | DECISION
```

It returns **structured** output: a list of evidenced `Claim`s (LOOKUP/EXPLAIN) or a full
`DecisionPacket` (DECISION, staff only). Read aloud in one go, that is information overload
for a farmer standing in a field.

**Goal:** a voice channel that feels like talking to a patient, respectful extension worker.
It hears Hindi, English or Hinglish, understands with as few questions as possible, answers in
**1–3 spoken sentences**, then offers **one** short follow-up ("Kya main batau ise kaise
badhayein?"). The rest of the answer is disclosed only as the listener asks for it.

**What voice is not:** new intelligence. It is a *view* over the existing orchestrator. It does
not widen the information boundary (INV-5), cannot approve anything (INV-1), and stores no
audio (INV-9).

**What exists today:** no voice code anywhere (web or API). Sarvam is used only for routing
chat-completions (`orchestrator/llm.py`) and `/translate` (`translation/sarvam.py`).
ADR-0008 marked voice "demo-grade Web Speech, no IVR". This spec supersedes the voice row of ADR-0008.

---

## 2. Research basis

### 2.1 Architecture: cascaded pipeline, not speech-to-speech
| Approach | Used by | Verdict for us |
|---|---|---|
| Speech-to-speech / full-duplex (one audio model) | ChatGPT GPT-Live, Gemini Live | ✗ ~10× cost, weak on rural Hindi, and **skips the text layer** where INV-3/5/8 checks, auditing and the DecisionPacket live. |
| **Cascaded STT → LLM → TTS, streaming** | Pipecat, LiveKit Agents, Sarvam's own Exotel reference agent | ✓ Every hop is inspectable text; 400–600 ms achievable with streaming; the transport can be swapped (browser now, phone later). |

Latency techniques we adopt: stream partial transcripts; stream TTS sentence by sentence; play a
short filler ("Ek second…") when the backend is slow; support barge-in (stop playback the moment
the user speaks).

### 2.2 Conversation design rules
From NVIDIA voice-agent best practices, the FarmChat (Microsoft Research India) and
Farmer.Chat (Digital Green) deployments, and general voice-UX literature:
1. 1–3 sentences a turn; never list more than 3 items.
2. **Progressive disclosure**: headline first, detail on request.
3. Infer before you ask. Fill slots from the farmer's own profile.
4. **Implicit confirmation** (the answer names what it understood) beats explicit confirmation.
   Explicit is kept for low-confidence or high-stakes turns.
5. Short replies ("haan", "nahi", "ji") must work reliably.
6. No markdown, URLs, tables or symbols in speech. Numbers said the local way, units always spoken.
7. Always provide a repair path and a way to reach a human.

### 2.3 Sarvam AI capabilities (docs.sarvam.ai, checked 2026-09-17)
- **STT, Saaras v3** (`/speech-to-text`): modes `transcribe | translate | verbatim | translit | codemix`;
  22 Indian languages; auto language detection. REST ≤30 s of audio; **streaming WebSocket** with
  partial transcripts, 16 kHz or 8 kHz PCM/WAV only.
- **TTS, Bulbul v3**: 30+ voices, 11 languages (10 Indic + English). REST ≤2500 chars; HTTP
  stream ≤3500; WebSocket ≤2500/msg (<500 recommended). Codecs mp3/wav/aac/opus/flac/pcm/**mulaw/alaw
  8 kHz** (telephony-ready for later).
- **LLM**: `sarvam-105b` via OpenAI-compatible `/v1/chat/completions` (already wired, ADR-0022).

> **Unverified until the spike (handoff Task 0):** exact WS URLs, auth header names for STT/TTS
> streaming, whether streaming STT returns a per-utterance confidence and a language code, and TTS
> `pace`/`speaker` parameter names. Do not hard-code guesses; read the live docs in Task 0 and
> record them in ADR-0024.

Sources:
[Sarvam STT overview](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/speech-to-text/overview) ·
[Sarvam TTS overview](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/text-to-speech/overview) ·
[Bulbul v3](https://www.sarvam.ai/blogs/bulbul-v3) ·
[Sarvam + Exotel voice agent](https://docs.sarvam.ai/api/integration/build-voice-agent-with-exotel) ·
[Sarvam IVR use-case](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/use-cases/ivr-contact-center) ·
[NVIDIA voice-agent best practices](https://github.com/NVIDIA/voice-agent-examples/blob/main/docs/BEST_PRACTICES.md) ·
[LiveKit: STT-LLM-TTS pipelines](https://livekit.com/blog/voice-agent-architecture-stt-llm-tts-pipelines-explained) ·
[Deepgram: voice agent pipeline design](https://deepgram.com/learn/voice-agent-architecture-stt-llm-tts-pipeline-design) ·
[FarmChat (IMWUT 2018)](https://mohitjaindr.github.io/pdfs/j2-imwut-2018.pdf) ·
[Farmer.Chat](https://www.researchgate.net/publication/384057603_FarmerChat_Scaling_AI-Powered_Agricultural_Services_for_Smallholder_Farmers)

---

## 3. Locked decisions

| # | Decision | Why |
|---|---|---|
| D1 | **In-app voice only** (web portal). Telephony (Exotel/Vobiz) is POST-MVP, but the core is transport-agnostic. | No number KYC or per-minute cost for MVP; a phone transport can be added later without touching the core. |
| D2 | **Hands-free with barge-in, plus a hold-to-talk button** as fallback. | Natural conversation; the button rescues noisy fields where VAD misfires. |
| D3 | **Hybrid composing**: LLM writes the spoken turn from grounded claims → deterministic **guard** → **template** fallback. | Natural wording without risking a mis-spoken number or dose. |
| D4 | Composer LLM = **Sarvam-105b** through `orchestrator/llm.py:structured`. | Best colloquial Hindi; already integrated; one vendor. |
| D5 | Languages: **Hindi, English, Hinglish** (Saaras `codemix`). | Matches Prayagraj demo, glossary and translation memory. More languages = config later. |
| D6 | **Implicit confirmation always**; **explicit** only if router confidence < 0.6, STT confidence < 0.7, a required slot has ≥2 candidates, or it is a staff DECISION. Slots pre-filled from profile. | Avoids the "annoying repeated questions" the product owner explicitly rejected. |
| D7 | **Farmer + FPO staff.** Staff voice is **read-only**: never approve/reject/execute by voice. Staff voice lives in **isolated files + one registration line**, so a single git revert removes it. No runtime flag. | INV-1 signatures must stay auditable on screen; product owner wants a clean rollback path for staff if it misbehaves. |
| D8 | **Server-side `VoiceSession`**: slots, `DisclosureQueue`, pending offer, last 4 turns. Idle TTL 15 min. Every spoken turn recorded in `voice_turn`; orchestrator calls still write `conversation_turn` (§12). | "haan" / "kyon" need context; the text assistant is stateless today. |
| D9 | **Transcripts only. Audio is never persisted.** | Simplest INV-9 posture; no new consent purpose. |
| D10 | **Degradation ladder** (§8), including: 2 consecutive slow turns (>6 s) → switch to text with "Network kamzor hai…". | Voice must fail softly, never go silent. |
| D11 | **Voice-first screen**: mic orb, live captions, a synced card for what is being spoken (number + unit + confidence chip), tap chips for offers. | Semi-literate users benefit from icons, numbers and taps; satisfies the "confidence chip" rule. |
| D12 | **WebSocket direct browser → FastAPI**, authenticated by a 60 s **voice ticket** JWT minted server-side. | Streaming + barge-in need a socket; the httpOnly session cookie never reaches JS. |
| D13 | **Staff DecisionPacket spoken bottom-line first** (§6.2). | The advice arrives in turn 1, not turn 3. |
| D14 | **Persona "Vardhak"**: respectful *aap*, glossary terms, pace ≈0.9, Indian number words, female default speaker (config), greets by name. | Trust and comprehension for rural listeners. |
| D15 | **Farmer scope mirrors the text assistant** (LOOKUP + REFUSE only). Code must make **farmer DECISION a later policy change, not a core change** (§9). | Product wants per-farmer decisions in a later version without rework. |
| D16 | **Router Hindi fix**: route on an English pivot + Devanagari/Hinglish keyword hints. | Today's keyword fallback and crop matcher are Latin-only (`router.py:229`, `:374`). |
| D17 | **Universal commands**: "ruko / bas" (stop), "phir se bolo" (repeat), "screen par dikhao" (show full view), "insaan se baat" (human). | Always-available escape hatches. |
| D18 | **Done** = golden spoken-turn tests + scripted demo round-trip. | |
| D19 | **Opening** = greeting + open question only: "Namaste {name} ji, main Vardhak hoon. Aap kya poochna chahenge?" Staff get the same (no proactive briefing). | Short, neutral start. |
| D20 | **Human handoff**: add `Organization.helpline_phone` (migration + seed); speak and show it with tap-to-call; record the turn. | No contact field exists today (`domain/models/organization.py`). |
| D21 | **Language switching**: start in `User.locale`; if STT detects a different language, ask once "Kya main English mein baat karun?" / "Shall I continue in Hindi?", then stick. | Respects the speaker without flip-flopping. |
| D22 | **Targets**: Android Chrome + desktop Chrome must pass; iOS Safari best-effort. One uvicorn worker, in-process session registry, ~20 concurrent sessions. | Matches the rural smartphone base and MVP infra; limit documented in ADR-0024. |
| D23 | **Staff access** = the existing `_guard` semantics in `api/chat.py:62`. No new roles. | |
| D24 | **Silence**: 8 s after the assistant stops speaking → nudge "Kuch aur jaanna hai?"; +12 s → "Theek hai, zarurat ho to mic dabayein. Dhanyavaad." and close the mic/STT stream. Session state kept 15 min; re-tap resumes. | Privacy and STT cost. |
| D25 | **Composer writes the target language directly**; relevant glossary terms injected as mandatory wording. No translate hop. | One hop, more natural, lower latency. |
| D26 | This spec + `docs/VOICE-HANDOFF.md` are the handoff artefacts. | |

---

## 4. Architecture

```
Browser (Chrome)                                   FastAPI (single worker)
┌──────────────────────────┐                       ┌────────────────────────────────────────────┐
│ /ask  → VoiceView         │  POST /api/voice/ticket (Next route, httpOnly cookie → Bearer)     │
│  use-voice-session.ts     │ ─────────────────────▶│ api/voice.py  POST /api/v1/voice/ticket     │
│  AudioWorklet 16k PCM     │                       │                                            │
│  energy VAD, barge-in     │  wss /api/v1/voice/ws?ticket=…                                     │
│  playback queue           │ ◀════════════════════▶│ voice/transport/browser_ws.py              │
│  orb · captions · card    │  JSON events + binary │   scope ← ticket ONLY (INV-5)              │
│  offer chips · hold-talk  │  PCM up / audio down  │   ▼                                        │
│  speechSynthesis fallback │                       │ voice/session.py  VoiceSession             │
└──────────────────────────┘                       │   1 speech/stt  (Saaras v3 stream | REST)  │
                                                    │   2 commands.match      (D17)              │
                                                    │   3 followup.match      (pending offer)    │
                                                    │   4 speech/pivot → orchestrator.chat.answer│
                                                    │   5 disclosure.plan_disclosure(answer,pol) │
                                                    │   6 composer.compose(chunk) → LLM|template │
                                                    │        └ guard.check                        │
                                                    │   7 spoken_numbers.verbalise               │
                                                    │   8 speech/tts  (Bulbul v3 stream)         │
                                                    │   9 record voice_turn (+conversation_turn) │
                                                    └────────────────────────────────────────────┘
```

### 4.1 Package layout (new)
```
apps/api/agrivardhak/voice/
├── __init__.py
├── contracts.py          Pydantic wire + domain shapes (§5)
├── session.py            VoiceSession + registry + state machine (§7)
├── disclosure.py         pure: AssistantAnswer + AudiencePolicy → DisclosureQueue (§6)
├── followup.py           pure: short-reply intent matcher
├── commands.py           pure: universal command matcher
├── lexicon.json          haan/nahi/kyon/kab/aur/ruko/… in Devanagari, Hinglish, English
├── composer.py           LLM → guard → template
├── guard.py              pure: spoken-turn safety + grounding checks (§6.3)
├── templates.py          pure: deterministic hi/en turns per LookupKey + packet section
├── spoken_numbers.py     pure: digits → spoken Hindi/English (paise, kg/quintal, lakh)
├── degrade.py            pure: counters → DegradeAction (§8)
├── prompts/spoken_turn.md
├── audience/
│   ├── __init__.py       AudiencePolicy + registry (farmer registered here)
│   ├── farmer.py
│   └── staff.py          ISOLATED (D7) — registered by one line in api/voice.py
├── speech/
│   ├── stt.py            Protocol SpeechToText + Transcript
│   ├── tts.py            Protocol TextToSpeech
│   ├── sarvam_stt.py
│   ├── sarvam_tts.py
│   ├── fixtures.py       deterministic adapters for tests / AGRI_USE_FIXTURES
│   └── pivot.py          English pivot for routing (D16)
└── transport/
    └── browser_ws.py
apps/api/agrivardhak/api/voice.py    ticket endpoint + WS route registration
```

Pure modules (`disclosure`, `followup`, `commands`, `guard`, `templates`, `spoken_numbers`,
`degrade`) take no DB, network or clock reads. The same discipline as `intelligence/` applies:
type hints, `mypy --strict` clean. Add `agrivardhak.voice.*` to the strict mypy overrides wherever
`domain`/`intelligence` are declared strict (`apps/api/pyproject.toml`).

---

## 5. Contracts

Pydantic v2, `ConfigDict(frozen=True)` for value objects. Money in paise, mass in kg (CLAUDE.md §6).

```python
class SpokenLanguage(StrEnum):  HI = "hi-IN"; EN = "en-IN"

class FollowUpIntent(StrEnum):
    YES = "yes"; NO = "no"; WHY = "why"; WHEN = "when"; MORE = "more"

class Command(StrEnum):
    STOP = "stop"; REPEAT = "repeat"; SHOW_SCREEN = "show_screen"; HUMAN = "human"

class Transcript(BaseModel):
    text: str                      # native script as returned by STT
    language: SpokenLanguage | None
    confidence: float | None       # None when provider does not return one → treat as 1.0
    is_final: bool

class DisclosureChunk(BaseModel):
    key: str                       # e.g. "lookup:MY_TASKS_TODAY:0", "packet:recommendation:0"
    kind: Literal["claims", "section", "refusal", "screen_only", "handoff"]
    claims: list[Claim]            # grounded input for composer; may be empty for refusal
    section: str | None            # DecisionPacket section name when kind == "section"
    offer: FollowUpIntent | None   # which follow-up this chunk invites
    offer_targets: dict[FollowUpIntent, str]   # intent → key of the chunk it unlocks
    card_ref: str | None           # what the screen highlights while speaking
    crop_protection: bool = False  # triggers INV-8 guard wording

class DisclosureQueue(BaseModel):
    chunks: dict[str, DisclosureChunk]
    head: str                      # key of the first chunk
    spoken: list[str] = []         # keys already delivered

class SpokenTurn(BaseModel):
    say: str                       # ≤3 sentences, digits allowed (verbalised later)
    offer: str | None              # the ONE follow-up question, or None at end of queue
    chunk_key: str
    source: Literal["llm", "template"]
    confirm: Literal["implicit", "explicit"]
    language: SpokenLanguage
    prompt_version: str | None

class AudiencePolicy(BaseModel):
    audience: Literal["farmer", "staff"]
    allowed_shapes: frozenset[ResponseShape]
    decision_order: tuple[str, ...]          # D13 order; used only if DECISION allowed
    screen_only_sections: frozenset[str]
    forbidden_utterance_patterns: tuple[str, ...]   # approve/execute phrases (staff)
    forbidden_reply_key: str                  # template key: "screen par dekhein"
```

**Wire events (JSON text frames; audio as binary frames):**

Client → server
| type | payload | notes |
|---|---|---|
| `start` | `{sample_rate: 16000, mode: "handsfree"\|"hold"}` | first message |
| *(binary)* | PCM16 LE mono 16 kHz, 20–40 ms frames | while listening |
| `end_of_speech` | `{}` | sent by hold-to-talk release; hands-free relies on server/STT endpointing |
| `barge_in` | `{}` | client VAD detected speech during playback; playback already stopped locally |
| `tap_offer` | `{intent: FollowUpIntent}` | chip tap ≡ spoken follow-up |
| `tap_command` | `{command: Command}` | |
| `playback_done` | `{chunk_key}` | starts the D24 silence timers |
| `stop` | `{}` | user closed voice view |

Server → client
| type | payload |
|---|---|
| `state` | `{state: VoiceState}` |
| `partial_transcript` | `{text}` |
| `final_transcript` | `{text, language, confidence}` |
| `filler` | `{text}` followed by its audio |
| `turn` | `SpokenTurn` + `{card: ClaimCard \| SectionCard \| HandoffCard \| null}` |
| `audio_start` / *(binary)* / `audio_end` | `{chunk_key, codec: "mp3"\|"pcm16", sample_rate}` |
| `tts_fallback` | `{text, language, pace}` → browser `speechSynthesis` speaks it |
| `degrade` | `{action: "to_text", reason: "slow_network"\|"repeated_failure", message}` |
| `show_screen` | `{conversation_id, packet_id \| null}` |
| `error` | `{code, message}` |
| `closed` | `{reason: "silence"\|"client"\|"expired"}` |

TypeScript mirrors of these live in `apps/web/src/lib/voice-contracts.ts`. *Note: CLAUDE.md
names `packages/contracts` for generated types, but that package does not exist in the repo;
the web tier hand-types payloads in `lib/api.ts` today. Follow the existing reality and add a
comment pointing at `voice/contracts.py` as the source of truth.*

---

## 6. Turning answers into speech

### 6.1 Farmer (LOOKUP / REFUSE)
- **LOOKUP**: claims in orchestrator order, chunked **≤2 claims per chunk**, at most 3 chunks spoken;
  remaining claims → a `screen_only` chunk ("Baaki jaankari screen par hai").
  Offer on each non-final chunk: `MORE` ("Aur batau?"). Offer on a chunk whose claim has
  `confidence < 0.6` or `below_floor`: `WHY` (FR-813: say what would raise it).
- **REFUSE / unknown crop**: one `refusal` chunk from `FARMER_REFUSAL` / `_unknown_crop` text
  (`orchestrator/chat.py:46-56,120`), no offer, no LLM.
- **EXPLAIN**: same as LOOKUP (claims come from the frozen packet, FR-819).

### 6.2 Staff DECISION (bottom line first, D13)
| Turn | Trigger | Content | Offer |
|---|---|---|---|
| T1 | answer arrives | recommendation[0] headline + expected_outcome + spoken confidence word | "Kyon, ya agla kadam?" (`WHY`/`MORE`) |
| T2a | `WHY` | situation + impact + top-2 evidence items | "Kab karna hai?" (`WHEN`) |
| T2b | `MORE` | recommendation[1] (max 3 recommendations ever spoken) | `WHY`/`MORE` |
| T3 | `WHEN` | next 2 dated schedule items | `MORE` if any left |
| — | "approve / manzoor / execute karo" | forbidden → "Approve karne ke liye screen par dekhein." + `show_screen` | none |
| — | anything in `screen_only_sections` (evidence list, drilldown, overrides, actions) | "Poori jaankari screen par hai." + `show_screen` | none |

Explicit confirm (D6) always precedes T1 for staff DECISION: "Aap is season ki {crop} yojana ke
baare mein pooch rahe hain na?" If the answer is `NO`, the session returns to listening, and the
next utterance is routed fresh.

Confidence word bands (from `ConfidenceBlock.overall`): ≥0.8 "kaafi bharosa", 0.6–0.8 "theek-thaak
bharosa", <0.6 "kam bharosa, kyonki …" (and read `what_would_raise_it[0]`).

**FR-818 reconciliation:** voice *defers* sections, it never deletes them. Every section stays
one tap ("screen par dikhao") away, and the full packet is persisted as today.

### 6.3 Composer and guard
```
compose(chunk, session) -> SpokenTurn
  if not llm.available() or chunk.kind in {refusal, screen_only, handoff}: return template
  prompt = prompts/spoken_turn.md  (+ glossary terms found in chunk, + slots, + language, + persona)
  raw = llm.structured(system, user, schema=SpokenTurnDraft, timeout=2.5s)
  if raw is None or not guard.check(raw, chunk): return template
  return raw (source="llm")
```
Guard rules, **all deterministic**; any failure → template, and log `guard_reason`:
1. **Grounding (INV-3, FR-817):** every number in `say`+`offer` (parse with
   `translation/quality.py:numbers`) must equal a `claim.magnitude` in the chunk, or a
   deterministic conversion of one (paise→rupees, kg→quintal). The LLM is told to write digits;
   verbalisation happens *after* the guard in `spoken_numbers.py`.
2. **Shape:** ≤3 sentences (split on `।` `.` `?` `!`), ≤350 chars, `offer` is exactly one question
   or null, no markdown/URL/emoji/bullets.
3. **Safety (INV-8):** if `chunk.crop_protection`, reject any dosage pattern
   (`\d+\s*(ml|g|kg|litre|लीटर|ग्राम)\s*(per|प्रति|/)`) or product-like token, and the turn must contain
   "label padhein" / "krishi salahkar se salah lein" (hi) or "read the label and consult your local
   agronomist" (en). Templates for crop protection are the IPM-order wording.
4. **Boundary (INV-5):** `say` may not contain a person name other than the session farmer's own
   name (checked against the claim `affected` set + session profile). Staff are exempt.
5. **Language:** `say` script matches the session language (reuse the `detect()` heuristic in
   `translation/service.py:68`); Hinglish in Latin script is allowed for `hi-IN` only if the STT
   input was Latin.

Implicit confirmation prefix (D6) is added by the composer, not the LLM, from filled slots:
"Aapke gehun ke liye — …". It is skipped when there are no slots.

### 6.4 Templates
`templates.py` holds a `dict[(template_key, language)] -> str.format`-style template.
- Keys cover every farmer `LookupKey` (`MY_FARM_PROFILE`, `MY_YIELD_GAP`, `MY_TASKS_TODAY`,
  `MY_SCHEMES`, `MY_ANNOUNCEMENTS`) and a generic claim template ("{statement}").
- They also cover each spoken DECISION turn, refusal, the greeting, nudge and close, the filler,
  STT failure, the language-switch question, "screen par dekhein", the human handoff, and "network
  kamzor hai".
- All Hindi strings are human-written. Add them to `apps/web/src/lib/strings.json` only if the
  web shows them; the API-side templates live in Python.

### 6.5 Spoken numbers
`verbalise(text, language)` converts digits to words just before TTS, and captions keep the digits:
- Hindi: Indian grouping (hazaar, lakh, crore); "₹2,150 प्रति क्विंटल" → "do hazaar ek sau pachaas
  rupaye prati quintal".
- Decimals: "3.8" → "teen dashamlav aath".
- Mass: kg values ≥100 in a price or yield context are spoken as quintal when the glossary says so.
- **Check first whether Bulbul v3 already reads Indian-grouped digits correctly** (Task 0). If it
  does, `verbalise` shrinks to unit expansion only. Don't build what the TTS already does.

---

## 7. VoiceSession state machine

```
            start/greet
 IDLE ───────────────────▶ SPEAKING ──playback_done──▶ AWAITING
                              ▲                          │ speech detected
                              │                          ▼
                              │                      LISTENING ──final_transcript──▶ UNDERSTANDING
                              │                          ▲                                 │
                              │ barge_in (stop TTS)──────┘                                 │
                              │                                                            ▼
                              └──────────── COMPOSING ◀── routed/answered ── (commands │ followup │ orchestrator)
 AWAITING ─8s─▶ nudge (SPEAKING) ─▶ AWAITING ─12s─▶ CLOSING ─▶ CLOSED (state kept 15 min)
```

`UNDERSTANDING` resolution order for a final transcript:
1. empty or low confidence (<0.4) → template "Awaaz saaf nahi aayi, phir se boliye?" and increment `stt_failures`.
2. `commands.match` → STOP (cancel TTS, go to AWAITING) · REPEAT (re-send last turn audio, no LLM) ·
   SHOW_SCREEN (`show_screen` event) · HUMAN (handoff chunk).
3. language differs from session and not yet asked → the D21 question, with `pending_offer=language_switch`.
4. `pending_offer` set and `followup.match` hits → advance the `DisclosureQueue` (no router call).
5. staff policy `forbidden_utterance_patterns` → forbidden template.
6. otherwise → a new question: `pivot` → `orchestrator.chat.answer(...)` → `plan_disclosure` → head
   chunk. If `plan.router_confidence < 0.6`, STT confidence < 0.7, or the staff answer is a DECISION,
   the first turn is the explicit confirm.

Session fields: `id (uuid7) = conversation_id`, `scope`, `policy`, `language`,
`language_switch_asked`, `slots {crop, plot_id, season}`, `queue`, `pending_offer`, `last_turn`,
`last_turn_audio` (in memory only, for REPEAT, never persisted), `history[-4:]`,
`stt_failures`, `slow_turns`, `anchor_packet_id`, `last_activity`.

Registry: `dict[UUID, VoiceSession]` behind an `asyncio.Lock`, swept every 60 s for idle > 900 s.
Documented limit: single worker, ~20 sessions (D22).

**Slots from profile:** at session start, load the farmer's active crop cycles through the existing
farmer lookup (`orchestrator/lookups/farmer.py`, `MY_FARM_PROFILE`). One active crop → `slots.crop`
is pre-filled. The router still owns interpretation; slots only drive the implicit-confirm prefix
and the explicit-confirm trigger ("≥2 candidates").

---

## 8. Degradation ladder (D10)

| Condition | Action |
|---|---|
| orchestrator not answered within 700 ms | speak filler "Ek second, dekh raha hoon…" once per turn |
| composer LLM > 2.5 s or guard fail | template turn (silent to user) |
| Sarvam TTS error/timeout (3 s) | `tts_fallback` event → browser `speechSynthesis` speaks the same text |
| Sarvam STT error | "Awaaz saaf nahi aayi…" + show chips/keyboard; `stt_failures += 1` |
| `stt_failures` or TTS failures reach 2 in a row | `degrade{to_text, repeated_failure}` → web switches to `ChatPanel` with the same `conversation_id` |
| end-of-speech → first audio byte > 6 s on **2 consecutive** turns | speak and show "Network kamzor hai, main likh kar bata raha hoon." → `degrade{to_text, slow_network}` |
| no LLM configured at all | whole flow works on templates + keyword router (FR-821) |

`degrade.py` is a pure function `(counters, last_latency_ms, event) -> DegradeAction`, so every row is
unit-testable.

---

## 9. Extension seam: farmer DECISION later (D15)

- The voice core (`session`, `disclosure`, `composer`) **never checks `audience`**. It consults
  `AudiencePolicy` only.
- `disclosure.plan_disclosure` handles every `ResponseShape`, DECISION included, for any policy. The
  DECISION order comes from `policy.decision_order`.
- To enable farmer decisions in a future version:
  1. orchestrator: allow DECISION for farmers in `router._shapes_for` plus a farmer-scoped packet
     (separate plan; touches INV-1/INV-6);
  2. voice: add `ResponseShape.DECISION` and a `decision_order` in `audience/farmer.py`.
  **No other voice file changes.** A test (`test_voice_extension_seam`) proves this with a stub policy.

## 10. Staff isolation (D7)

- All staff-specific voice behaviour lives in `voice/audience/staff.py` and
  `apps/web/src/components/voice/staff-voice-entry.tsx`.
- It is wired by **one line** in `api/voice.py` (`register_policy(staff.POLICY)`) and **one import**
  in `app/(fpo)/assistant/page.tsx`.
- Rollback = revert the commit that adds those (keep it a separate commit: "feat(voice): staff
  read-only voice"). If no staff policy is registered, a staff ticket is rejected with 403 `voice not
  available for this role`, and farmer voice is unaffected.

## 11. Invariants mapping
| Invariant | How voice honours it |
|---|---|
| INV-1 | No voice path writes Approval/EXECUTED; staff approve phrases → screen. Test asserts it. |
| INV-2 | "kyon" on a packet reads the frozen packet/snapshot via the EXPLAIN path; never re-runs. |
| INV-3 | Guard: every spoken number traces to a claim magnitude with evidence. |
| INV-4 | Discrepancy claims are spoken with "do jaankari mel nahi kha rahi" wording, never resolved. |
| INV-5 | Scope comes only from the ticket; lookups are unchanged; guard blocks other names. |
| INV-8 | Crop-protection guard + IPM templates; never product+dose. |
| INV-9 | No audio stored; transcripts go in `conversation_turn` / `voice_turn` like typed questions. |

## 12. Data changes
- `conversation_turn`: add `channel VARCHAR(8) NOT NULL DEFAULT 'text'` (`text|voice`). `chat.answer()`
  gains a keyword `channel: str = "text"` that it passes to `_record`. The row is still written
  inside `answer()`, before any speech exists, so it cannot hold the spoken text; the table is
  append-only.
- **New append-only table `voice_turn`** (no `updated_at`). One row per *spoken* turn, including
  follow-ups, commands, greetings and nudges that never reach the orchestrator (FR-820 "every turn
  recorded"): `id uuid7`, `conversation_id` (= session id), `conversation_turn_id NULL FK` (set when
  the turn came from `answer()`), `organization_id`, `actor_user_id`, `farmer_id NULL`, `kind`
  (`greeting|answer|followup|command|confirm|nudge|close|handoff|forbidden|degrade|stt_failure`),
  `transcript TEXT NULL`, `transcript_language`, `stt_confidence NUMERIC NULL`, `chunk_key`,
  `say TEXT`, `offer TEXT NULL`, `source (llm|template)`, `confirm (implicit|explicit|null)`,
  `guard_reason NULL`, `prompt_version NULL`, `latency_ms_first_audio INT NULL`, `created_at`.
  **No audio columns** (D9).
- `organization`: add `helpline_phone VARCHAR(20) NULL`; the seed sets a clearly synthetic number for the
  demo FPO (CLAUDE.md §8.5: label `SYNTHETIC — DEMO ONLY`).
- New config (`AGRI_` prefix): `sarvam_stt_url`, `sarvam_stt_ws_url`, `sarvam_stt_model="saaras:v3"`,
  `sarvam_tts_url`, `sarvam_tts_ws_url`, `sarvam_tts_model="bulbul:v3"`, `voice_speaker`,
  `voice_pace=0.9`, `voice_compose_timeout_seconds=2.5`, `voice_tts_timeout_seconds=3.0`,
  `voice_filler_ms=700`, `voice_slow_turn_seconds=6.0`, `voice_silence_nudge_seconds=8`,
  `voice_silence_close_seconds=12`, `voice_session_ttl_seconds=900`, `voice_ticket_ttl_seconds=60`,
  `voice_max_sessions=20`.

## 13. Out of scope (v1)
Telephony/IVR number · audio storage · long-term memory across days · voice approvals · farmer
DECISION packets · languages beyond hi/en/Hinglish · iOS Safari guarantee · multi-worker session
store · STT word-error-rate eval harness · WhatsApp voice notes.

## 14. Docs to update in the build
- ADR-0024 (new).
- `docs/SRS.md`: UI-06 → MUST; new FR-822…FR-828; acceptance scenario 8.
- `docs/MVP-SCOPE.md`: voice row, the `:29` vs `:219` contradiction, and the demo script.
- `docs/ARCHITECTURE.md`: `:465` stale endpoint, plus a voice layer.
- `docs/GLOSSARY.md`: VoiceSession, SpokenTurn, DisclosureQueue, AudiencePolicy.
- `context.md`: T-05 and the ADR link.
- `CLAUDE.md` stack table: the Voice row becomes "Sarvam Saaras v3 STT + Bulbul v3 TTS over WebSocket;
  browser speechSynthesis fallback".
- `scripts/progress.py`: a new Deliverable.

Exact wording for the FR entries is in the handoff, Task 1.
