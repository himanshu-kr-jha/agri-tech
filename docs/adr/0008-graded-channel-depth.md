# ADR-0008 — Graded depth across three farmer channels, not three shallow channels

Date: 2026-08-22 · Status: Accepted

## Context

Three farmer-facing channels are in scope: web (Hindi/English), WhatsApp and voice. Discovery
established why — farmers have limited connectivity and limited literacy, and WhatsApp plus
Hindi was the explicit answer to the accessibility question.

Three channels at full depth is not achievable in 72 hours. Dropping two of them weakens the
inclusion story that the brief's theme rests on. Building all three shallowly produces three
things that each look unfinished.

## Decision

Grade the depth deliberately, and say so.

| Channel | Depth | What ships |
|---|---|---|
| **Web (Hi/En)** | Complete | Farmer portal: today's actions, my farm, assistant, schemes, calendar. Mobile-first at 360px, ≤200 KB for the daily view. |
| **Voice** | Demo-grade | Browser Web Speech API for Hindi/English input on the assistant field; TTS for the answer. No telephony, no IVR tree. ~3 hours of work. |
| **WhatsApp** | One thin path | Outbound notification of approved farmer-facing actions, plus inbound free-text routed to the Farmer Assistant. Sandbox number, no conversation state machine. |

**Go/no-go checkpoint at hour 24.** If WhatsApp sandbox provisioning is not complete, the channel
is cut and notifications fall back to in-app. That call is made at hour 24, not drifted past it.

## Consequences

**Easier.** The channel each judge will actually touch is finished. The accessibility claim is
demonstrated live rather than asserted on a slide. The scope is bounded and the failure mode is
pre-decided rather than discovered at hour 60.

**Harder.** Voice is browser-dependent — Hindi ASR quality varies by device, and there is no
telephony fallback for a farmer without a smartphone, which is precisely the population the
theme centres. WhatsApp handles one turn well and multi-turn poorly.

**Accepted, and stated honestly in the pitch.** Claiming full IVR coverage we have not built
would be the worse outcome. The correct framing is: the decision layer is channel-agnostic, and
these are the three surfaces we brought to the demo.

## Alternatives considered

- **Web only.** Cleanest execution, but abandons the inclusion differentiator that the theme
  is built on.
- **WhatsApp-first.** Matches farmer reality best, but conversational state, media handling and
  a review-gated sandbox make it a poor primary surface for a judged demo.
- **Real telephony IVR (Exotel/Twilio).** The right long-term answer for non-smartphone farmers.
  A week of work, and a phone number provisioning dependency we cannot control. POST-MVP.
