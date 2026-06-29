// Centralized API client (CLAUDE.md: "All API calls centralized in api.ts"). Field
// names mirror gateway/app/schemas/admin.py exactly -- never re-derive them.
export const API_BASE: string = import.meta.env.VITE_API_BASE || "http://localhost:8000";

// Phase 30: admin-track JWT (`deps.require_role`), separate from the shared-secret
// `X-Admin-Token` this app used before real RBAC existed. Stored in sessionStorage so
// it doesn't survive a closed tab, mirroring web-app's session token convention.
const ADMIN_TOKEN_KEY = "cogniguard_admin_token";

export function setAdminToken(token: string): void {
  sessionStorage.setItem(ADMIN_TOKEN_KEY, token);
}

export function getAdminToken(): string | null {
  return sessionStorage.getItem(ADMIN_TOKEN_KEY);
}

export function clearAdminToken(): void {
  sessionStorage.removeItem(ADMIN_TOKEN_KEY);
}

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
  updated_at?: string | null;
  score_id?: string | null;
  risk_band?: string | null;
  final_risk_score?: number | null;
  reason_codes?: Record<string, unknown>[] | null;
  amplifiers?: Record<string, unknown>[] | null;
}

export interface CaseUpdate {
  status?: CaseStatus;
  assigned_to?: string;
  note?: string;
}

export interface ModelVersionOut {
  model_id: string;
  version?: string | null;
  stage?: "staging" | "production" | "archived" | null;
  model_type?: string | null;
  metrics: Record<string, number>;
  artifact_uri?: string | null;
  deployed_at?: string | null;
}

export interface ModelOut {
  model_name: string;
  versions: ModelVersionOut[];
}

export interface DriftColumnReport {
  skipped?: boolean;
  reason?: string;
  psi?: number;
  ks_stat?: number;
  ks_pvalue?: number;
  n_live?: number;
  n_reference?: number;
  breached?: boolean;
}

export interface DriftReportOut {
  window: { live_start: string; live_end: string; reference_start: string; reference_end: string };
  columns: Record<string, DriftColumnReport>;
  outcome: {
    n_resolved: number;
    n_confirmed_fraud: number;
    n_false_positive: number;
    precision: number | null;
  };
  breaches: Record<string, unknown>[];
  retrained_models: string[];
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

export interface AdminLoginResponse {
  token: string;
  analyst_id: string;
  role: "admin" | "analyst";
  full_name?: string | null;
}

interface ApiResult<T> {
  status: number;
  body: T;
}

export function adminLogin(
  email: string,
  password: string,
): Promise<ApiResult<AdminLoginResponse>> {
  return fetch(`${API_BASE}/api/v1/admin/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  }).then(async (res) => ({ status: res.status, body: (await res.json()) as AdminLoginResponse }));
}

async function adminRequest<T>(path: string, init: RequestInit = {}): Promise<ApiResult<T>> {
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
    Authorization: `Bearer ${getAdminToken() ?? ""}`,
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

export function listModels(): Promise<ApiResult<ModelOut[]>> {
  return adminRequest("/api/v1/admin/models");
}

export function getDrift(): Promise<ApiResult<DriftReportOut>> {
  return adminRequest("/api/v1/admin/drift");
}

// D2: Auth timeline
export interface AuthTimelineEventOut {
  event_id: string;
  event_type?: string | null;
  challenge_type?: string | null;
  decision?: string | null;
  risk_band?: string | null;
  device_label?: string | null;
  created_at?: string | null;
}

export function getAuthTimeline(userId: string): Promise<ApiResult<AuthTimelineEventOut[]>> {
  return adminRequest(`/api/v1/admin/users/${userId}/auth-timeline`);
}

// D3: Device intelligence
export interface GeoEntryOut {
  ip_address?: string | null;
  city?: string | null;
  country?: string | null;
  seen_at?: string | null;
}

export interface DeviceIntelOut {
  device_id: string;
  os?: string | null;
  os_version?: string | null;
  browser?: string | null;
  is_rooted: boolean;
  is_emulator: boolean;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  trust_class?: string | null;
  trust_score?: number | null;
  linked_user_count: number;
  event_count: number;
  geo_trend: GeoEntryOut[];
}

export function getDeviceIntel(deviceId: string): Promise<ApiResult<DeviceIntelOut>> {
  return adminRequest(`/api/v1/admin/devices/${deviceId}`);
}

// D4: SHAP explanation
export interface ShapFeatureOut {
  feature: string;
  shap_value: number;
  feature_value?: number | null;
}

export interface ShapExplanationOut {
  score_id: string;
  model_version?: string | null;
  top_features: ShapFeatureOut[];
  ai_explanation?: string | null;
}

export interface FactoryResetOut {
  status: string;
  tables_truncated: string[];
  redis: string;
}

export function explainScore(scoreId: string): Promise<ApiResult<ShapExplanationOut>> {
  return adminRequest(`/api/v1/admin/explain/${scoreId}`, { method: "POST" });
}

// D5: LLM investigation assistant
export interface InvestigationResultOut {
  case_id: string;
  provider: string;
  summary: string;
  risk_factors: string[];
  recommendation?: string | null;
  generated_at?: string | null;
}

export function investigateCase(caseId: string): Promise<ApiResult<InvestigationResultOut>> {
  return adminRequest(`/api/v1/admin/cases/${caseId}/investigate`, { method: "POST" });
}

export function factoryReset(): Promise<ApiResult<FactoryResetOut>> {
  return adminRequest("/api/v1/admin/factory-reset", { method: "POST" });
}
