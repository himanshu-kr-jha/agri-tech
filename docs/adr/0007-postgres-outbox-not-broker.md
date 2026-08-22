# ADR-0007 — Postgres transactional outbox instead of a message broker

Date: 2026-08-22 · Status: Accepted

## Context

The system is event-shaped: `RecommendationApproved`, `HealthObserved`, `PolicyEventDetected`,
`OutcomeRecorded`. Events drive the calendar, notifications, the audit trail and the learning
loop. The instinct is to reach for Kafka, Redis Streams or RabbitMQ.

Scale reality: 30 organizations × 2,000 farmers is roughly tens of thousands of events per day —
well within a single Postgres table's comfortable range. Demo reality: every additional service
is another thing that can fail on stage and another thing that must run offline.

## Decision

A **transactional outbox** in Postgres. Every domain state change writes a `domain_event` row in
the same transaction as the change. A dispatcher polls unpublished rows every 5 seconds and
fans out to notifications, WhatsApp and downstream jobs, marking `published_at`.

Event ids are UUIDv7, so the table is naturally time-ordered without a sequence.

## Consequences

**Easier.** Atomicity for free: a state change and its event cannot diverge, which is the bug a
broker introduces and then makes you solve with idempotency keys and dead-letter queues. The
event log is queryable with SQL — invaluable for the audit trail and for reconstructing what the
system knew. One fewer service in Docker Compose, and the demo runs fully offline.

**Harder.** Polling adds up to 5 seconds of latency, which is irrelevant here. Throughput is
bounded by Postgres, which caps us well above the design target of NFR-201. No consumer groups,
no replay-from-offset semantics.

**Accepted.** If throughput ever becomes the constraint, the outbox is the standard on-ramp to a
broker: point a relay at the same table and consumers do not change.

## Alternatives considered

- **Kafka / Redpanda.** Rejected: operational weight, and the dual-write problem it creates
  between the database and the log.
- **Redis Streams.** Lighter, but still a second service and still a dual write, for a durability
  guarantee weaker than Postgres.
- **Direct synchronous calls, no events.** Rejected: the audit trail and the learning loop both
  need an ordered record of what happened, and inline calls make approval flows brittle.
- **`LISTEN`/`NOTIFY` without a table.** Rejected: not durable — a notification delivered while
  no listener is connected is simply lost.
