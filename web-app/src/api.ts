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

// Data-driven enrollment progress (gateway/app/schemas/enrollment.py) -- drives the
// "Security Profile Calibration N/10" banner.
export interface EnrollmentProgress {
  collected: number;
  required: number;
  complete: boolean;
  just_finalized?: boolean;
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
  // Continuous identity verification (gateway Phase 20-22).
  trust_score?: number | null;
  behavior_match_score?: number | null;
  device_trust?: number | null;
  enrollment?: EnrollmentProgress | null;
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

export function verifyPaymentStepUp(
  challengeId: string,
  otpOrAssertion: string,
): Promise<ApiResult<PaymentScoreResponse>> {
  return request("/api/v1/payment/step-up/verify", {
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

// Phase 28's customer banking read schemas (gateway/app/schemas/banking.py) --
// deliberately carry no risk/trust fields (see that file's docstring on the
// customer/SOC split); field names mirror it verbatim.
export interface ProfileOut {
  user_id: string;
  customer_ref: string | null;
  full_name: string | null;
  masked_email: string | null;
  masked_phone: string | null;
  kyc_level: string | null;
  account_status: string;
  member_since: string | null;
}

export interface AccountOut {
  account_id: string;
  masked_account_number: string | null;
  account_type: string | null;
  balance: number | null;
  currency: string | null;
  status: string | null;
  opened_at: string | null;
}

export interface TransactionOut {
  transaction_id: string;
  account_id: string | null;
  beneficiary_name: string | null;
  masked_beneficiary_account: string | null;
  amount: number | null;
  currency: string | null;
  transfer_type: string | null;
  channel: string | null;
  status: string | null;
  initiated_at: string | null;
  completed_at: string | null;
}

export interface BeneficiaryOut {
  beneficiary_id: string;
  name: string | null;
  masked_account_number: string | null;
  bank_code: string | null;
  beneficiary_type: string | null;
  is_verified: boolean;
  transfer_count: number;
  added_at: string | null;
}

export interface TrustedDeviceOut {
  device_id: string;
  label: string | null;
  is_trusted: boolean;
  last_used_at: string | null;
}

export interface ActiveSessionOut {
  session_id: string;
  device_label: string | null;
  location: string | null;
  started_at: string | null;
}

export interface SecuritySettingsOut {
  trusted_devices: TrustedDeviceOut[];
  active_sessions: ActiveSessionOut[];
}

function authedGet<T>(path: string, token: string): Promise<ApiResult<T>> {
  return request(path, { headers: { Authorization: `Bearer ${token}` } });
}

export function getProfile(token: string): Promise<ApiResult<ProfileOut>> {
  return authedGet("/api/v1/banking/profile", token);
}

export function listAccounts(token: string): Promise<ApiResult<AccountOut[]>> {
  return authedGet("/api/v1/banking/accounts", token);
}

export function listTransactions(
  token: string,
  limit = 50,
): Promise<ApiResult<TransactionOut[]>> {
  return authedGet(`/api/v1/banking/transactions?limit=${limit}`, token);
}

export function listBeneficiaries(token: string): Promise<ApiResult<BeneficiaryOut[]>> {
  return authedGet("/api/v1/banking/beneficiaries", token);
}

export function getSecuritySettings(token: string): Promise<ApiResult<SecuritySettingsOut>> {
  return authedGet("/api/v1/banking/security-settings", token);
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
