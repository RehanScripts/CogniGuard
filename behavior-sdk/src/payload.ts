import type { BehaviorPayload } from "./types.js";

export type UnsignedPayload = Omit<BehaviorPayload, "nonce" | "seq" | "ts" | "integrity_sig">;

/**
 * Marks a leaf as a Pydantic `float`-typed field. `gateway/app/services/integrity.py`'s
 * `canonical_metrics()` re-serializes the parsed `BehaviorPayload` model via
 * `model_dump(mode="json")`, and Pydantic coerces float-annotated fields (keystroke
 * down/up, the three context timing fields, every `derived_features` value,
 * `ae_recon_error`) to Python `float` regardless of what the wire JSON looked like —
 * so a whole-number value like
 * `12` round-trips through Python's `json.dumps` as `"12.0"`, not `"12"`. Untyped dict
 * passthrough fields (`mouse`, `touch`) get no such coercion, so their numbers are left
 * as plain JS numbers here, matching Python's literal pass-through.
 */
const PYFLOAT = Symbol("pyfloat");

interface PyFloat {
  [PYFLOAT]: true;
  v: number;
}

export function pyFloat(v: number): PyFloat {
  return { [PYFLOAT]: true, v };
}

function isPyFloat(x: unknown): x is PyFloat {
  return typeof x === "object" && x !== null && PYFLOAT in x;
}

function formatPyFloat(n: number): string {
  return Number.isInteger(n) ? `${n}.0` : `${n}`;
}

/**
 * Recursively sorts object keys and serializes with no whitespace — must byte-for-byte
 * match Python's `json.dumps(metrics, sort_keys=True, separators=(",", ":"))`.
 *
 * The sort is unconditional and depth-independent: every object encountered at every
 * level of the tree (top-level metrics, nested blocks, objects inside arrays) is
 * re-sorted by key here, exactly as `sort_keys=True` re-sorts every dict Python's
 * encoder visits, at any depth. Neither side ever relies on caller-supplied insertion
 * order — that's what makes the two implementations agree byte-for-byte regardless of
 * the order fields were assigned when the payload was built. Never replace this with
 * an "only sort the top level" shortcut.
 */
export function canonical(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (isPyFloat(value)) return formatPyFloat(value.v);
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    const keys = Object.keys(obj).sort();
    return `{${keys.map((k) => `${JSON.stringify(k)}:${canonical(obj[k])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function buildCanonicalMetricsTree(p: UnsignedPayload): unknown {
  return {
    channel: p.channel,
    source: p.source,
    action: { type: p.action.type },
    keystroke: p.keystroke
      ? {
          events: p.keystroke.events.map((e) => ({ key: e.key, down: pyFloat(e.down), up: pyFloat(e.up) })),
          field_id: p.keystroke.field_id,
        }
      : null,
    mouse: p.mouse
      ? {
          moves: p.mouse.moves.map((m) => ({ x: m.x, y: m.y, t: m.t })),
          clicks: p.mouse.clicks.map((c) => ({ t: c.t, dur: c.dur })),
        }
      : null,
    touch: p.touch ? { swipes: p.touch.swipes.map((s) => ({ len: s.len, dur: s.dur, vx: s.vx, vy: s.vy })) } : null,
    derived_features: p.derived_features
      ? Object.fromEntries(Object.entries(p.derived_features).map(([k, v]) => [k, pyFloat(v)]))
      : null,
    ae_recon_error: p.ae_recon_error === null ? null : pyFloat(p.ae_recon_error),
    ae_model_version: p.ae_model_version,
    context: {
      submitted_at: p.context.submitted_at,
      page: p.context.page,
      pre_txn_dwell_ms: pyFloat(p.context.pre_txn_dwell_ms),
      session_age_s: pyFloat(p.context.session_age_s),
      correction_rate: pyFloat(p.context.correction_rate),
    },
  };
}

async function sha256Digest(input: string): Promise<ArrayBuffer> {
  return crypto.subtle.digest("SHA-256", new TextEncoder().encode(input));
}

function toHex(buf: ArrayBuffer): string {
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** `key=sha256(signingSecret+nonce)`, `msg=nonce‖canonical(metrics)‖fingerprint‖ts` —
 * mirrors `gateway/app/services/integrity.py::compute_signature` exactly. */
async function hmacSha256Hex(signingSecret: string, nonce: string, msg: string): Promise<string> {
  const keyBytes = await sha256Digest(signingSecret + nonce);
  const hmacKey = await crypto.subtle.importKey("raw", keyBytes, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", hmacKey, new TextEncoder().encode(msg));
  return toHex(sig);
}

let seqCounter = 0;

/** Resets the monotonic seq counter — call on a fresh login/session (a fresh nonce
 * cycle), matching the server's per-binding Redis floor starting back at 0. */
export function resetSequence(): void {
  seqCounter = 0;
}

export async function fetchNonce(apiBase: string): Promise<{ nonce: string; expiresAt: string }> {
  const res = await fetch(`${apiBase}/auth/nonce`);
  if (!res.ok) {
    throw new Error(`fetchNonce failed: ${res.status} ${res.statusText}`);
  }
  const body = (await res.json()) as { nonce: string; expires_at: string };
  return { nonce: body.nonce, expiresAt: body.expires_at };
}

export async function signPayload(
  partial: UnsignedPayload,
  nonce: string,
  signingSecret: string,
): Promise<BehaviorPayload> {
  const ts = new Date().toISOString();
  const seq = ++seqCounter;
  const canonicalStr = canonical(buildCanonicalMetricsTree(partial));
  const msg = nonce + canonicalStr + partial.device.fingerprint + ts;
  const integrity_sig = await hmacSha256Hex(signingSecret, nonce, msg);
  return { ...partial, nonce, seq, ts, integrity_sig };
}
