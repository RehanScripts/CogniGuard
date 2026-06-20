// Centralized API client (CLAUDE.md: "All API calls centralized in api.ts"). Field
// names mirror gateway/app/schemas/decision.py exactly -- never re-derive them.
import type { BehaviorPayload } from "@cogniguard/behavior-sdk";

export const API_BASE: string = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export type RiskBand = "low" | "medium" | "high" | "very_high";
export type DecisionAction = "allow" | "verify" | "block";
export type ChallengeType = "OTP" | "MPIN" | "FINGERPRINT" | "PASSKEY" | "VOICE_READBACK";
export type TransferType = "IMPS" | "NEFT" | "RTGS" | "UPI";

export interface ReasonCode {
  code: string;
  detail: string;
  sigma?: number | null;
}

export interface AmplifierFired {
  code: string;
  multiplier: number;
  detail: string;
}

export interface StepUpChallenge {
  challenge_type: ChallengeType;
  assurance: "light" | "strong";
  challenge_id: string;
}

export interface TxnControls {
  cooling_until: string | null;
  manual_amount: boolean;
  coercion_check: boolean;
  reconfirm: "APP_PUSH" | "EMAIL" | null;
}

export interface Hardening {
  action: "DELAY" | "CAPTCHA" | "LOCKOUT";
  scope: "ip" | "device";
  retry_after_s: number;
}

export interface DecisionResponse {
  action: DecisionAction;
  entity_type: "login" | "transaction";
  risk_score: number;
  risk_band: RiskBand;
  required_factors: string[];
  reason_codes: ReasonCode[];
  amplifiers: AmplifierFired[];
  action_sensitivity: "low" | "medium" | "high";
  step_up: StepUpChallenge | null;
  txn_controls: TxnControls | null;
  session_token: string | null;
  hardening: Hardening | null;
  integrity: "OK" | "INTEGRITY_REJECT";
  degraded_mode: boolean;
  model_version: string;
}

export interface PaymentScoreResponse extends DecisionResponse {
  base_score: number;
}

interface ApiResult<T> {
  status: number;
  body: T;
}

async function request<T>(path: string, init: RequestInit): Promise<ApiResult<T>> {
  const res = await fetch(`${API_BASE}${path}`, init);
  const body = (await res.json()) as T;
  return { status: res.status, body };
}

const JSON_HEADERS = { "Content-Type": "application/json" };

export function register(
  username: string,
  password: string,
): Promise<ApiResult<{ user_id?: string; status?: string; detail?: string }>> {
  return request("/api/v1/auth/register", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ username, password }),
  });
}

export function setConsent(
  username: string,
  action: "GRANT" | "WITHDRAW",
): Promise<ApiResult<{ user_id?: string; consent_status?: string; detail?: string }>> {
  return request("/api/v1/auth/consent", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ username, action, consent_version: "v1" }),
  });
}

export function login(
  username: string,
  password: string,
  behavior: BehaviorPayload,
): Promise<ApiResult<DecisionResponse>> {
  return request("/api/v1/auth/login", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ username, password, behavior }),
  });
}

export function verifyStepUp(
  challengeId: string,
  otpOrAssertion: string,
): Promise<ApiResult<DecisionResponse>> {
  return request("/api/v1/auth/step-up/verify", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ challenge_id: challengeId, otp_or_assertion: otpOrAssertion }),
  });
}

export interface PaymentScoreRequestBody {
  amount: number;
  beneficiary_id?: string;
  beneficiary_vpa?: string;
  transfer_type: TransferType;
  channel: "web" | "mobile";
  behavior: BehaviorPayload;
}

export function scorePayment(
  token: string,
  req: PaymentScoreRequestBody,
): Promise<ApiResult<PaymentScoreResponse>> {
  return request("/api/v1/payment/score", {
    method: "POST",
    headers: { ...JSON_HEADERS, Authorization: `Bearer ${token}` },
    body: JSON.stringify(req),
  });
}

const SESSION_TOKEN_KEY = "cogniguard_session_token";

// JWT is short-lived (gateway JWT_TTL_MINUTES=30) and cleared on tab close --
// simplest reasonable choice for a demo over persisting it in localStorage.
export function setSessionToken(token: string): void {
  sessionStorage.setItem(SESSION_TOKEN_KEY, token);
}

export function getSessionToken(): string | null {
  return sessionStorage.getItem(SESSION_TOKEN_KEY);
}

export function clearSessionToken(): void {
  sessionStorage.removeItem(SESSION_TOKEN_KEY);
}
