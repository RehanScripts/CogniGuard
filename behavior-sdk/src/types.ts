/**
 * Mirrors gateway/app/schemas/behavior.py field-for-field. Keep these two files in sync —
 * the gateway's Pydantic model is the source of truth.
 */

export type Channel = "web" | "mobile";
export type Source = "web_sdk" | "mobile_edge";
export type ActionType =
  | "LOGIN"
  | "VIEW_BALANCE"
  | "ADD_PAYEE"
  | "TRANSFER"
  | "CHANGE_CONTACT"
  | "RAISE_LIMIT";

export interface KeyEvent {
  key: string; // "x" placeholder for secret fields; "Backspace" tracked. NEVER the real char.
  down: number; // ms offset
  up: number; // ms offset
}

export interface DeviceInfo {
  fingerprint: string;
  ua: string;
  screen: string;
  timezone: string;
  language: string;
  platform: string; // "web" | "android"
  is_rooted: boolean;
  is_emulator: boolean;
}

export interface ActionBlock {
  type: ActionType;
}

export interface KeystrokeBlock {
  events: KeyEvent[];
  field_id: string;
}

export interface MouseMove {
  x: number;
  y: number;
  t: number;
}

export interface MouseClick {
  t: number;
  dur: number;
}

export interface MouseBlock {
  moves: MouseMove[];
  clicks: MouseClick[];
}

export interface TouchSwipe {
  len: number;
  dur: number;
  vx: number;
  vy: number;
}

export interface TouchBlock {
  swipes: TouchSwipe[];
}

export interface ContextBlock {
  submitted_at: string;
  page: string;
  pre_txn_dwell_ms: number;
  session_age_s: number;
  correction_rate: number;
}

export interface BehaviorPayload {
  channel: Channel;
  source: Source;
  // Telemetry integrity binding (NFR-5)
  nonce: string;
  seq: number;
  ts: string; // client ISO8601 timestamp (skew-checked)
  integrity_sig: string; // HMAC-SHA256(nonce ‖ canonical(metrics) ‖ fingerprint ‖ ts)

  device: DeviceInfo;
  action: ActionBlock;

  // web_sdk: raw timing/motion features
  keystroke: KeystrokeBlock | null;
  mouse: MouseBlock | null;
  touch: TouchBlock | null;
  // mobile_edge: pre-computed features only (raw streams stay on device)
  derived_features: Record<string, number> | null;

  context: ContextBlock;
}
