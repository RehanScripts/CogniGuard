// Centralized API client (CLAUDE.md: "All API calls centralized in api.ts"). Field
// names mirror gateway/app/schemas/admin.py exactly -- never re-derive them.
export const API_BASE: string = import.meta.env.VITE_API_BASE || "http://localhost:8000";

// deps.require_admin is a flat shared-secret check against settings.jwt_secret (no
// real RBAC exists yet, gateway/app/deps.py) -- mirrors the same demo simplification
// behavior-sdk's signingSecret already accepts. There is no admin login page in this
// app by design (Implementation.md's bank-dashboard file list has none).
const ADMIN_TOKEN: string = import.meta.env.VITE_ADMIN_TOKEN || "change_me_dev_only_super_secret";

export type RiskBand = "low" | "medium" | "high" | "very_high";
export type CaseStatus = "open" | "investigating" | "confirmed_fraud" | "false_positive" | "closed";

export interface EventOut {
  score_id: string;
  entity_type: string;
  entity_id?: string | null;
  user_id?: string | null;
  final_risk_score?: number | null;
  risk_band?: RiskBand | null;
  action?: string | null;
  model_version?: string | null;
  latency_ms?: number | null;
  scored_at?: string | null;
}

export interface UserDetailOut {
  user: Record<string, unknown>;
  devices: Record<string, unknown>[];
  recent_events: EventOut[];
  quarantined_samples: number;
}

export interface CaseOut {
  case_id: string;
  user_id?: string | null;
  transaction_id?: string | null;
  alert_type?: string | null;
  severity?: string | null;
  status: CaseStatus;
  assigned_to?: string | null;
  created_at?: string | null;
  resolved_at?: string | null;
}

export interface CaseUpdate {
  status?: CaseStatus;
  assigned_to?: string;
  note?: string;
}

export interface PolicyDict {
  scoring_mode: "stacked" | "weighted";
  weights: Record<string, number>;
  thresholds: Record<string, number>;
  action_sensitivity: Record<string, unknown>;
  amplifiers: Record<string, number>;
  stepup: Record<string, unknown>;
  cooling_off: Record<string, unknown>;
  hardening: Record<string, unknown>;
}

interface ApiResult<T> {
  status: number;
  body: T;
}

async function adminRequest<T>(path: string, init: RequestInit = {}): Promise<ApiResult<T>> {
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
    "X-Admin-Token": ADMIN_TOKEN,
  };
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  const body = (await res.json()) as T;
  return { status: res.status, body };
}

export function listEvents(
  params: { band?: string; user_id?: string; entity_type?: string; limit?: number } = {},
): Promise<ApiResult<EventOut[]>> {
  const query = new URLSearchParams();
  if (params.band) query.set("band", params.band);
  if (params.user_id) query.set("user_id", params.user_id);
  if (params.entity_type) query.set("entity_type", params.entity_type);
  query.set("limit", String(params.limit ?? 50));
  return adminRequest(`/api/v1/admin/events?${query.toString()}`);
}

export function getUserDetail(userId: string): Promise<ApiResult<UserDetailOut>> {
  return adminRequest(`/api/v1/admin/users/${userId}`);
}

export function getPolicy(): Promise<ApiResult<{ active_policy: PolicyDict }>> {
  return adminRequest("/api/v1/admin/policy");
}

export function putPolicy(
  update: Partial<PolicyDict>,
): Promise<ApiResult<{ active_policy: PolicyDict }>> {
  return adminRequest("/api/v1/admin/policy", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
}

export function listCases(
  params: { status?: string; user_id?: string; limit?: number } = {},
): Promise<ApiResult<CaseOut[]>> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.user_id) query.set("user_id", params.user_id);
  query.set("limit", String(params.limit ?? 50));
  return adminRequest(`/api/v1/admin/cases?${query.toString()}`);
}

export function patchCase(caseId: string, update: CaseUpdate): Promise<ApiResult<CaseOut>> {
  return adminRequest(`/api/v1/admin/cases/${caseId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
}
