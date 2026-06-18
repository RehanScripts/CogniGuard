import { KeystrokeCapture, MouseCapture, TouchCapture } from "./events.js";
import { computeFingerprint } from "./fingerprint.js";
import { fetchNonce, resetSequence, signPayload } from "./payload.js";
import type { ActionType, BehaviorPayload, ContextBlock, KeyEvent } from "./types.js";

export * from "./types.js";
export { canonical, pyFloat, resetSequence } from "./payload.js";
export { extractMobileFeatures } from "./edge.js";
export { computeFingerprint } from "./fingerprint.js";
export { KeystrokeCapture, MouseCapture, TouchCapture } from "./events.js";

export interface CogniGuardConfig {
  apiBase: string;
  /** Opaque signing secret mirroring the gateway's `jwt_secret` (see integrity.py /
   * PROGRESS.md known-gap note) — the demo web-app injects the dev value. */
  signingSecret: string;
}

export interface AttachOptions {
  /** Field ids/names (or CSS-id-free names) treated as secret even if not `type="password"`. */
  secretFields?: string[];
  page?: string;
}

interface FieldCapture {
  fieldId: string;
  capture: KeystrokeCapture;
}

let config: CogniGuardConfig | null = null;
let fieldCaptures: FieldCapture[] = [];
let mouseCapture: MouseCapture | null = null;
let touchCapture: TouchCapture | null = null;
let attachedPage = "";
let sessionStartedAt: number | null = null;

function requireConfig(): CogniGuardConfig {
  if (!config) throw new Error("CogniGuard.init() must be called before use");
  return config;
}

function init(cfg: CogniGuardConfig): void {
  config = cfg;
  sessionStartedAt = performance.now();
}

function detach(): void {
  for (const f of fieldCaptures) f.capture.destroy();
  fieldCaptures = [];
  mouseCapture?.destroy();
  touchCapture?.destroy();
  mouseCapture = null;
  touchCapture = null;
}

function attach(formEl: HTMLFormElement, opts: AttachOptions = {}): void {
  requireConfig();
  detach();
  const clockOrigin = performance.now();
  const secretFieldIds = new Set(opts.secretFields ?? []);
  const fields = Array.from(formEl.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>("input, textarea"));

  fieldCaptures = fields.map((field) => {
    const fieldId = field.id || field.name || "field";
    const secret = field.type === "password" || secretFieldIds.has(fieldId);
    return { fieldId, capture: new KeystrokeCapture(field, { fieldId, secret, clockOrigin }) };
  });
  mouseCapture = new MouseCapture(document, clockOrigin);
  touchCapture = new TouchCapture(document, clockOrigin);
  attachedPage = opts.page ?? "";
  sessionStartedAt = sessionStartedAt ?? clockOrigin;
}

function mergeKeystrokeEvents(): { events: KeyEvent[]; fieldId: string } {
  if (fieldCaptures.length === 0) return { events: [], fieldId: "" };
  let busiest = fieldCaptures[0]!;
  let maxCount = -1;
  const drained = fieldCaptures.map((f) => ({ fieldId: f.fieldId, events: f.capture.drain() }));
  for (let i = 0; i < drained.length; i++) {
    if (drained[i]!.events.length > maxCount) {
      maxCount = drained[i]!.events.length;
      busiest = fieldCaptures[i]!;
    }
  }
  const events = drained.flatMap((d) => d.events).sort((a, b) => a.down - b.down);
  return { events, fieldId: maxCount > 0 ? busiest.fieldId : "" };
}

function buildContext(action: ActionType): ContextBlock {
  const now = performance.now();
  const sessionAgeS = sessionStartedAt === null ? 0 : (now - sessionStartedAt) / 1000;
  return {
    submitted_at: new Date().toISOString(),
    page: attachedPage,
    pre_txn_dwell_ms: 0,
    session_age_s: sessionAgeS,
    correction_rate: 0,
  };
}

async function collect(action: ActionType = "LOGIN"): Promise<BehaviorPayload> {
  const cfg = requireConfig();
  const device = await computeFingerprint();
  const { events, fieldId } = mergeKeystrokeEvents();
  const { moves, clicks } = mouseCapture?.drain() ?? { moves: [], clicks: [] };
  const swipes = touchCapture?.drain() ?? [];
  const context = buildContext(action);

  const { nonce } = await fetchNonce(cfg.apiBase);

  return signPayload(
    {
      channel: "web",
      source: "web_sdk",
      device,
      action: { type: action },
      keystroke: events.length > 0 ? { events, field_id: fieldId } : null,
      mouse: moves.length > 0 || clicks.length > 0 ? { moves, clicks } : null,
      touch: swipes.length > 0 ? { swipes } : null,
      derived_features: null,
      context,
    },
    nonce,
    cfg.signingSecret,
  );
}

function startContinuous(sessionToken: string, intervalMs = 10000): () => void {
  const cfg = requireConfig();
  let stopped = false;

  const tick = async (): Promise<void> => {
    if (stopped) return;
    try {
      const payload = await collect("VIEW_BALANCE");
      await fetch(`${cfg.apiBase}/api/v1/behavior/ingest`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${sessionToken}`,
        },
        body: JSON.stringify(payload),
      });
    } catch {
      // Best-effort: a single failed tick shouldn't kill the continuous loop;
      // the next interval retries with a fresh nonce/seq.
    }
  };

  const handle = setInterval(tick, intervalMs);
  return () => {
    stopped = true;
    clearInterval(handle);
  };
}

export const CogniGuard = {
  init,
  attach,
  detach,
  collect,
  startContinuous,
  resetSequence,
};
