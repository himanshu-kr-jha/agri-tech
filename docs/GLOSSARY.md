# Glossary — AgriVardhak Ubiquitous Language

Use these terms exactly, in code, in the UI, in prompts and in conversation. Where a term has
a tempting synonym, the synonym is listed as **not**.

---

## Organizational

| Term | Meaning |
|---|---|
| **Organization** | The collective. `type ∈ {FPO, PACS, SHG, FPC, COOPERATIVE}`. All intelligence operates on this abstraction. *Not:* "the FPO" in code. |
| **FPO** | Farmer Producer Organization — a legally registered collective of farmers, usually a producer company. The primary implementation for the hackathon. |
| **PACS** | Primary Agricultural Credit Society — village-level cooperative credit body. |
| **SHG** | Self-Help Group — small savings/credit collective, usually women-led. |
| **Membership** | A farmer's relationship to an organization: role, dates, shares, patronage. A farmer may hold several. |
| **GovernanceProfile** | Type-specific governance rules attached to an Organization. |
| **OrgResource** | Something the organization owns that constrains decisions: working capital, warehouse, cold storage, machinery, vehicle, processing unit, input inventory. |
| **Announcement** | Organization communication with an explicit `visibility`. The mechanism by which information legitimately crosses to farmers. |

## People & land

| Term | Meaning |
|---|---|
| **Farmer** | The person cultivating. *Not:* "user", "member" (a Membership is the relationship, not the person). |
| **Farm** | An operational grouping of plots run by one operator. |
| **Plot** | The atomic unit of cultivation, with area and optionally a boundary polygon. *Not:* "field", "land", "parcel". |
| **PlotTenure** | Who holds a plot, how (`OWNED / LEASED / SHARECROPPED / JOINT / ALLOTTED / OTHER`), for what share, over what period. Deliberately separate from ownership-as-a-column. |
| **Operator** | The farmer who actually runs a farm day to day; may hold no tenure. |

## Agriculture

| Term | Meaning |
|---|---|
| **Crop** / **Variety** | Reference data. A CropCycle grows a Variety, not a Crop. |
| **CropCycle** | One crop grown on one plot in one season. The central temporal entity of the system — nearly every module joins here. |
| **Season** | `KHARIF · RABI · ZAID · PERENNIAL` plus a year. |
| **FarmResource** | Any productive asset on a farm: `CROP · LIVESTOCK · POULTRY · FISHERY · COMPOST · MANURE · AGROFORESTRY · WATER · EQUIPMENT · STRUCTURE`. |
| **ResourceFlow** | A directed link between two farm resources (`FEED · FERTILITY · WATER · ENERGY · RESIDUE · LABOUR · INCOME`). The data form of integrated farming. |
| **InputApplication** | A recorded application of seed, nutrient, crop protection, water, labour or energy to a crop cycle. |
| **Grade** | Quality classification `A · B · C · REJECT` plus the parameters that determined it. |
| **IPM** | Integrated Pest Management. Our default posture: prevention → cultural → biological → chemical. |

## Data & provenance

| Term | Meaning |
|---|---|
| **Observation** | An append-only record of a value with full provenance. The unit of truth for volatile facts. |
| **Provenance** | `source_type` + `source_ref` + `observed_at` + `recorded_at` + `confidence` + `verification_status`. |
| **Trust weight** | Base confidence attached to a source type. |
| **Confidence decay** | Halving of confidence over an attribute-specific half-life. |
| **Stale** | An observation older than its attribute's staleness threshold. A UI state, not a value change. |
| **DataDiscrepancy** | Recorded conflict between sources for one (subject, attribute). Surfaced, never silently resolved. |
| **DataSource** | A registered origin of data, with trust weight and cadence. |
| **ExternalRecord** | A raw payload fetched from an external source, retained for evidence citation. |
| **Fixture** | Offline stand-in data used when a live source is unavailable. Always UI-labelled. |
| **Publisher** | The authority that *authored* a dataset (e.g. DES/CACP). Distinct from access route. |
| **Access route** | Where we actually fetched it (e.g. `api.data.gov.in`). Never recorded as the publisher. |
| **Cap lift** | Raising a confidence ceiling once a value is sourced *and* verified. Requires a named verifier — ADR-0014. |
| **Authoritative source** | A source whose costs may enter a ranked comparison (CACP/DES). ADR-0012. |
| **Advisory source** | A sourced-but-not-authoritative source (ICAR, university study). May inform a suggestion, never a ranking. ADR-0012. |
| **Scraper checkpoint** | Per-scraper opaque cursor recording the last extracted record, so a batch resumes rather than restarts. |
| **Canonical text** | The source's own published wording, frozen. For Hindi-only schemes this is Hindi — ADR-0015. |
| **Derived translation** | A translation of canonical text, carrying its own translator identity and version. Rules never derive from it. |
| **MSP announced** | CACP's notified price for a crop-season. A policy fact, not a price a farmer can necessarily get. ADR-0016. |
| **Procurement available** | Whether a centre is open, in window, in spec and with quota. Gates whether MSP is reachable. |
| **Effective realization** | What the farmer actually nets after deductions and settlement lag. Never conflated with MSP or market price. |

## Intelligence & decisions

| Term | Meaning |
|---|---|
| **Intelligence module** | A pure function producing `Finding`s with confidence and evidence. Six of them. |
| **Finding** | One evidenced statement from a module, with magnitude, confidence, evidence and affected set. |
| **Prediction** | A claim about reality (expected yield 4.2 t, conf 0.81). Evaluated against the actual. *Not* approvable. |
| **Recommendation** | A proposed action. Evaluated by adherence and outcome. *Not* scored for accuracy. |
| **Orchestrator** | The LLM layer that reconciles module outputs, applies cross-domain overrides, and produces a Decision Packet. |
| **DecisionPacket** | The canonical answer: Situation, Impact, Recommendation, Expected outcome, Confidence, Evidence, Actions, Schedule, Drill-down (+ Overrides). Nine sections, fixed order. |
| **EvidenceRef** | A pointer from a claim to the observation, external record, prediction or row that supports it. |
| **EvidenceSnapshot** | The immutable, hashed freeze of every input used to generate a recommendation. Makes past decisions permanently explainable. |
| **Cross-domain override** | The orchestrator declining a single module's finding on stronger evidence from other domains. Always stated explicitly. |
| **Approval** | A human's recorded decision on a recommendation, including an `approved_value` that may differ from the recommended one. |
| **Intervention** | An executed action, with adherence. |
| **Adherence** | `followed ∈ {YES, PARTIAL, NO, UNKNOWN}` + fidelity + delay + deviation notes. |
| **Outcome** | The observed result against a baseline over a period, with the external conditions that prevailed. |
| **Attribution** | How much of an outcome is plausibly explained by the intervention: `HIGH · MODERATE · UNCERTAIN · CONFOUNDED`. |

## Market

| Term | Meaning |
|---|---|
| **Buyer** | A purchasing counterparty with quantity, price, quality requirement, delivery window, location, payment terms and reliability history. |
| **DemandSignal** | An expressed or inferred requirement for a commodity, quantity, grade and window. |
| **Lot** | An aggregation of produce from one or more crop cycles offered as one unit. |
| **Effective Price** | Buyer price net of logistics, handling, quality loss, transaction costs, storage and financing. The number that actually matters. *Not:* "price". |
| **Transaction Attractiveness** | Composite score over effective price, reliability, rejection risk, payment delay, quantity fit and distance. Component breakdown always shown. |
| **Negotiation brief** | The asking price plus the evidence supporting it, prepared for a specific buyer conversation. |
| **BuyerMatch** | A scored pairing of a lot with a buyer. |

## Risk & policy

| Term | Meaning |
|---|---|
| **Risk domain** | One of: climate, weather, crop health, market, policy, supply chain, global. |
| **RiskRegisterEntry** | Risk + probability + impact + farmers affected + area + recommended action + owner + status. |
| **Causal chain** | The explicit reasoning from an external event to organization-specific exposure and a recommended action. Structured, not prose. |
| **Exposure** | Quantified consequence: tonnes, farmers, acres, ₹ at risk. |
| **Risk-adjusted value** | `expected_value − λ · downside_deviation`, with λ shown. |

## Government schemes

| Term | Meaning |
|---|---|
| **Scheme** | A government programme with machine-evaluable eligibility rules plus the original text. |
| **EligibilityAssessment** | Per-farmer, per-scheme result: `ELIGIBLE · LIKELY_ELIGIBLE · INSUFFICIENT_DATA · NOT_ELIGIBLE`, with rule-by-rule detail. |
| **Document gap** | A specific missing document blocking an otherwise eligible application. |
| **SchemeApplication** | `DISCOVERED → ELIGIBLE → DOCUMENTS_PENDING → APPLIED → UNDER_REVIEW → APPROVED / REJECTED`. |

## Governance

| Term | Meaning |
|---|---|
| **ContextScope** | The actor + organization + subject filter applied in the repository layer. The enforcement point for the information boundary. |
| **Visibility scope** | `OWNER · ORG_INTERNAL · SHARED_WITH_MEMBERS · PUBLIC`. |
| **Information boundary** | The rule that only officially shared information crosses from the organization context to a farmer, or between farmers. Enforced by data, not by prompts. |
| **Consent** | Per-purpose (`SERVICE_DELIVERY · ORG_ANALYTICS · MODEL_IMPROVEMENT · ANONYMIZED_RESEARCH`), revocable, versioned. |
| **AuditRecord** | Who did what, when, on what evidence, with what authority. Immutable. |
| **DomainEvent** | An append-only record of a domain state change, written in the same transaction as the change. |

---

## Words we do not use

| Avoid | Use instead | Why |
|---|---|---|
| "AI decided" | "AI recommended" | The AI never decides (INV-1). |
| "maximum profit" | "sustainable farmer income" | Promising maximum profit is indefensible and off-thesis. |
| "user" (for a farmer) | "farmer" | The farmer is a person in a domain, not a seat. |
| "field" (for land) | "plot" | "Field" is ambiguous with form fields. |
| "score" alone | the named metric | An unnamed score is a black box. |
| "the FPO" in code | `Organization` | The abstraction is what makes PACS/SHG possible. |
| "smart" / "AI-powered" in UI copy | say what it does | Judges and farmers both discount adjectives. |
| "predicted" for a recommendation | "recommended" | INV-6. |
