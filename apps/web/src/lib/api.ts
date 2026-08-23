import { sessionToken } from "@/lib/session";

/**
 * Server-side API client.
 *
 * The web tier never touches the database (ADR-0001): every read goes through FastAPI so
 * that authorization, provenance resolution and the information boundary have exactly one
 * enforcement point. That is why this file exists rather than a Prisma schema.
 *
 * The bearer token comes from the signed-in session — an httpOnly cookie the browser cannot
 * read (see `lib/session.ts`). `AGRI_DEV_TOKEN` is still honoured as a fallback so the older
 * `make dev-env` workflow and any scripts built on it keep working; a real session wins.
 *
 * Every function here is async because reading the cookie is. That is a small tax for the
 * property it buys: there is no code path where a token reaches the browser.
 */

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Card {
  key: string;
  label: string;
  value: number | string | null;
  unit: string | null;
  confidence: number | null;
  detail: string | null;
  href: string | null;
  synthetic: boolean;
}

export interface Organization {
  id: string;
  name: string;
  type: string;
  district: string;
  state: string;
  is_synthetic: boolean;
}

export interface Dashboard {
  organization: Organization;
  generated_at: string;
  cards: Card[];
}

export interface FarmerRow {
  id: string;
  name: string;
  village: string | null;
  block: string | null;
  tract: string | null;
  area_acres: number;
  is_synthetic: boolean;
}

export interface FarmerList {
  total: number;
  limit: number;
  offset: number;
  farmers: FarmerRow[];
}

export interface Provenance {
  confidence: number;
  source_type: string;
  observed_at: string;
  is_stale: boolean;
  has_open_discrepancy: boolean;
}

export interface FarmerDetail {
  farmer: FarmerRow & { district: string };
  plots: {
    id: string;
    label: string;
    area_acres: number;
    soil_type: string | null;
    irrigation_source: string | null;
    provenance: Provenance | null;
  }[];
  crop_cycles: {
    id: string;
    crop: string;
    variety: string;
    season: string;
    status: string;
    area_acres: number;
    sowing_date: string | null;
    expected_harvest: string | null;
    crop_health_pct: number | null;
    health_confidence: number | null;
    health_is_stale: boolean | null;
  }[];
  lot_contributions: {
    lot: string;
    crop: string;
    quantity_kg: number;
    grade: string | null;
  }[];
}

// --------------------------------------------------------------------------- decisions

export interface EvidenceRef {
  kind: string;
  id: string;
  label: string;
  as_of: string;
}

export interface AffectedSet {
  farmer_ids: string[];
  plot_ids: string[];
  crop_cycle_ids: string[];
  lot_ids: string[];
  buyer_ids: string[];
  area_sqm: string | null;
  quantity_kg: string | null;
  value_paise: number | null;
}

export interface Claim {
  statement: string;
  magnitude: string | null;
  unit: string | null;
  confidence: number;
  evidence: EvidenceRef[];
  affected: AffectedSet | null;
}

export interface PacketAction {
  title: string;
  rationale: string;
  recommendation_type: string;
  target_type: string;
  target_id: string | null;
  value_paise: number | null;
  value_unit: string | null;
  expected_impact: Record<string, unknown>;
  risks: string[];
  alternatives: string[];
  confidence: number;
  evidence: EvidenceRef[];
}

export interface OverrideNote {
  overridden_key: string;
  overridden_module: string;
  reason: string;
  prevailing_evidence: EvidenceRef[];
}

export interface ConfidenceBlock {
  overall: number;
  per_section: Record<string, number>;
  below_floor: boolean;
  what_would_raise_it: string[];
  degraded_inputs: string[];
}

export interface Packet {
  question: string;
  scope: { organization_id: string; audience: string; season: string | null };
  situation: Claim[];
  impact: Claim[];
  recommendation: PacketAction[];
  expected_outcome: Claim[];
  confidence: ConfidenceBlock;
  evidence: EvidenceRef[];
  actions: { role: string; task: string; due_on: string | null }[];
  drilldown: {
    farmer_ids: string[];
    plot_ids: string[];
    crop_cycle_ids: string[];
    lot_ids: string[];
    buyer_ids: string[];
  };
  overrides: OverrideNote[];
  generated_at: string;
  snapshot_id: string;
  prompt_version: string;
  model_id: string;
}

export interface AskResult {
  packet_id: string;
  snapshot_id: string;
  content_hash: string;
  plan: string[];
  elapsed_ms: number;
  recommendation_ids: string[];
  packet: Packet;
}

export interface Approval {
  id: string;
  decision: string;
  role_exercised: string;
  approved_value_paise: number | null;
  rationale: string | null;
  decided_at: string;
}

export interface Recommendation {
  id: string;
  packet_id: string | null;
  type: string;
  title: string;
  reasoning: string;
  status: string;
  confidence: number;
  recommended_value_paise: number | null;
  value_unit: string | null;
  expected_impact: Record<string, unknown>;
  risks: string[] | null;
  alternatives: string[] | null;
  evidence: EvidenceRef[];
  snapshot_id: string;
  created_at: string;
  approvals: Approval[];
  awaiting: string | null;
}

export interface DecisionSummary {
  id: string;
  question: string;
  generated_at: string;
  overall_confidence: number;
  model_id: string | null;
  recommendations: number;
}

export interface DecisionDetail {
  id: string;
  question: string;
  generated_at: string;
  packet: Packet;
  evidence_snapshot: {
    id: string;
    content_hash: string | null;
    captured_at: string | null;
    module_versions: Record<string, string>;
    coefficients: Record<string, unknown>;
  };
  recommendations: Recommendation[];
}

export interface RiskEntry {
  id: string;
  domain: string;
  title: string;
  likelihood: string;
  impact: string;
  status: string;
  farmers_affected: number | null;
  area_affected_acres: number | null;
  value_at_risk_paise: number | null;
  recommended_action: string | null;
  owner_role: string | null;
  review_on: string | null;
  detail: Record<string, unknown> | null;
  evidence: EvidenceRef[] | null;
}

export interface MarketLot {
  id: string;
  label: string;
  crop: string | null;
  quantity_kg: number;
  grade: string | null;
  ready_date: string | null;
  contributors: number;
  offers: {
    buyer: string | null;
    price_paise_per_kg: number | null;
    grade_required: string | null;
    distance_km: number | null;
    payment_terms_days: number | null;
    rejection_rate: number | null;
  }[];
}

export interface BriefingItem {
  kind: string;
  headline: string;
  detail: string | null;
  href: string | null;
  count: number | null;
  value_paise: number | null;
  /** The unit `value_paise` is in — a buyer-selection value is paise per kg, not a total. */
  unit: string | null;
}

export interface Briefing {
  generated_at: string;
  quiet: boolean;
  needs_decision: BriefingItem[];
  closing_soon: BriefingItem[];
  watch: BriefingItem[];
  data_health: BriefingItem[];
}

export interface Impact {
  interventions: number;
  adherence: Record<string, number>;
  attributions: number;
  attribution_strength: Record<string, number>;
  unattributable: number;
  predictions_scored: number;
  mean_absolute_error: number | null;
  note: string;
}

export interface FarmerToday {
  farmer: { id: string; name: string; village: string | null; block: string | null; is_synthetic: boolean };
  crops: {
    id: string;
    crop: string;
    variety: string;
    area_acres: number;
    sown_on: string | null;
    expected_harvest: string | null;
    health_pct: number | null;
    health_confidence: number | null;
    health_observed_at: string | null;
  }[];
  lot_contributions: { lot: string; crop: string; quantity_kg: number; grade: string | null }[];
  boundary_note: string;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function authHeaders(): Promise<Record<string, string>> {
  const token = await sessionToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: await authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new ApiError(res.status, `${path} returned ${res.status}`);
  }
  return (await res.json()) as T;
}

export const api = {
  dashboard: () => get<Dashboard>("/api/v1/fpo/dashboard"),
  farmers: (params: { tract?: string; block?: string; limit?: number; offset?: number } = {}) => {
    const search = new URLSearchParams();
    if (params.tract) search.set("tract", params.tract);
    if (params.block) search.set("block", params.block);
    search.set("limit", String(params.limit ?? 50));
    search.set("offset", String(params.offset ?? 0));
    return get<FarmerList>(`/api/v1/fpo/farmers?${search}`);
  },
  farmer: (id: string) => get<FarmerDetail>(`/api/v1/fpo/farmers/${id}`),
  market: () => get<{ lots: MarketLot[] }>("/api/v1/fpo/market"),
  ask: (question: string) => post<AskResult>("/api/v1/assistant/ask", { question }),
  decisions: () => get<{ decisions: DecisionSummary[] }>("/api/v1/decisions"),
  decision: (id: string) => get<DecisionDetail>(`/api/v1/decisions/${id}`),
  replay: (id: string) =>
    get<{ identical: boolean; matches_original: Record<string, boolean> }>(
      `/api/v1/decisions/${id}/replay`,
    ),
  recommendations: (status?: string) =>
    get<{ recommendations: Recommendation[] }>(
      `/api/v1/recommendations${status ? `?status=${status}` : ""}`,
    ),
  riskRegister: () => get<{ entries: RiskEntry[] }>("/api/v1/risk-register"),
  briefing: () => get<Briefing>("/api/v1/briefing"),
  impact: () => get<Impact>("/api/v1/impact"),
  farmerToday: () => get<FarmerToday>("/api/v1/farmer/today"),
  approve: (id: string, body: { rationale?: string; approved_value_paise?: number }) =>
    post<Recommendation>(`/api/v1/recommendations/${id}/approve`, body),
  reject: (id: string, body: { rationale: string }) =>
    post<Recommendation>(`/api/v1/recommendations/${id}/reject`, body),
  execute: (id: string, body: { action_taken?: string }) =>
    post<Recommendation>(`/api/v1/recommendations/${id}/execute`, body),
};

/** Tract labels. The keys are the values the API returns; do not translate them in place. */
async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(await authHeaders()),
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    // The API returns RFC 9457 problem details; surface the detail rather than the status
    // alone, because a 409 from the approval gate carries the reason a human needs to read.
    let detail = `${path} returned ${res.status}`;
    try {
      const problem = await res.json();
      detail = problem.detail ?? problem.title ?? detail;
    } catch {
      // a non-JSON error body is still an error; the status text stands
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const TRACT_LABEL: Record<string, string> = {
  GANGA_PAR: "Ganga-par",
  DOAB: "Doab",
  YAMUNA_PAR: "Yamuna-par",
};
