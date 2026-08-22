/**
 * Server-side API client.
 *
 * The web tier never touches the database (ADR-0001): every read goes through FastAPI so
 * that authorization, provenance resolution and the information boundary have exactly one
 * enforcement point. That is why this file exists rather than a Prisma schema.
 *
 * The dev token below is a stand-in until NextAuth lands. It is issued by the API's own
 * `issue_token` in dev only and carries the CEO role — a real session will replace it, and
 * the API does not care which produced it because it verifies either way.
 */

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEV_TOKEN = process.env.AGRI_DEV_TOKEN ?? "";

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

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: DEV_TOKEN ? { Authorization: `Bearer ${DEV_TOKEN}` } : {},
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
};

/** Tract labels. The keys are the values the API returns; do not translate them in place. */
export const TRACT_LABEL: Record<string, string> = {
  GANGA_PAR: "Ganga-par",
  DOAB: "Doab",
  YAMUNA_PAR: "Yamuna-par",
};
