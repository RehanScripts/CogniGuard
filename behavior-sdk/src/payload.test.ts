import { createHash, createHmac } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { canonical, fetchNonce, pyFloat, resetSequence, signPayload, type UnsignedPayload } from "./payload.js";

beforeEach(() => resetSequence());

// Implementation.md Phase 17's shared golden vector -- the same fixture
// gateway/tests/test_integrity_mobile.py (Python) and Phase 18's Android
// CanonicalTest/SignerTest (Kotlin) assert against, byte-for-byte.
const GOLDEN_FIXTURE_PATH = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../gateway/tests/fixtures/golden_canonical_mobile.json",
);
const golden = JSON.parse(readFileSync(GOLDEN_FIXTURE_PATH, "utf-8")) as {
  secret: string;
  payload: UnsignedPayload & { nonce: string; seq: number; ts: string };
  canonical: string;
  integrity_sig: string;
};

describe("golden canonical vector (Phase 17, shared with Python + Kotlin)", () => {
  it("canonical() over the golden mobile payload matches the fixture string exactly", () => {
    const { nonce: _nonce, seq: _seq, ts: _ts, ...partial } = golden.payload;
    const canonicalStr = canonical({
      channel: partial.channel,
      source: partial.source,
      action: { type: partial.action.type },
      keystroke: null,
      mouse: null,
      touch: null,
      derived_features: Object.fromEntries(
        Object.entries(partial.derived_features!).map(([k, v]) => [k, pyFloat(v)]),
      ),
      ae_recon_error: pyFloat(partial.ae_recon_error!),
      ae_model_version: partial.ae_model_version,
      context: {
        submitted_at: partial.context.submitted_at,
        page: partial.context.page,
        pre_txn_dwell_ms: pyFloat(partial.context.pre_txn_dwell_ms),
        session_age_s: pyFloat(partial.context.session_age_s),
        correction_rate: pyFloat(partial.context.correction_rate),
      },
    });
    expect(canonicalStr).toBe(golden.canonical);
  });

  it("HMAC over the golden canonical string matches the fixture signature exactly", () => {
    const key = createHash("sha256").update(golden.secret + golden.payload.nonce).digest();
    const msg = golden.payload.nonce + golden.canonical + golden.payload.device.fingerprint + golden.payload.ts;
    const sig = createHmac("sha256", key).update(msg).digest("hex");
    expect(sig).toBe(golden.integrity_sig);
  });
});

describe("canonical", () => {
  it("sorts nested object keys and uses no whitespace", () => {
    const value = { b: 1, a: { d: 2, c: 3 }, e: [3, 1, 2] };
    expect(canonical(value)).toBe('{"a":{"c":3,"d":2},"b":1,"e":[3,1,2]}');
  });

  it("renders null for missing optional blocks", () => {
    expect(canonical(null)).toBe("null");
    expect(canonical({ keystroke: null })).toBe('{"keystroke":null}');
  });

  it("formats pyFloat leaves the way Python's json.dumps formats float fields", () => {
    expect(canonical(pyFloat(12))).toBe("12.0");
    expect(canonical(pyFloat(0))).toBe("0.0");
    expect(canonical(pyFloat(12.5))).toBe("12.5");
  });

  it("leaves plain (non-pyFloat) numbers as JS would render them", () => {
    expect(canonical({ t: 5 })).toBe('{"t":5}');
  });

  it("is independent of object key insertion order, at every nesting depth", () => {
    const treeA = {
      channel: "web",
      action: { type: "LOGIN" },
      keystroke: {
        field_id: "username",
        events: [
          { key: "x", down: pyFloat(12), up: pyFloat(98) },
          { key: "x", down: pyFloat(210), up: pyFloat(305) },
        ],
      },
      context: { page: "login", submitted_at: "2026-06-17T12:00:01Z" },
    };
    // Same logical content as treeA, but every object's keys declared in reverse
    // order — mirrors a Python dict built/iterated with a different key order.
    const treeB = {
      context: { submitted_at: "2026-06-17T12:00:01Z", page: "login" },
      keystroke: {
        events: [
          { up: pyFloat(98), down: pyFloat(12), key: "x" },
          { up: pyFloat(305), down: pyFloat(210), key: "x" },
        ],
        field_id: "username",
      },
      action: { type: "LOGIN" },
      channel: "web",
    };

    expect(canonical(treeA)).toBe(canonical(treeB));
  });
});

describe("signPayload", () => {
  const basePartial: UnsignedPayload = {
    channel: "web",
    source: "web_sdk",
    device: {
      fingerprint: "device-abc",
      ua: "test-ua",
      screen: "1920x1080",
      timezone: "Asia/Kolkata",
      language: "en-IN",
      platform: "web",
      is_rooted: false,
      is_emulator: false,
    },
    action: { type: "LOGIN" },
    keystroke: {
      events: [
        { key: "x", down: 12, up: 98 },
        { key: "x", down: 210, up: 305 },
      ],
      field_id: "username",
    },
    mouse: { moves: [{ x: 1, y: 2, t: 5 }], clicks: [{ t: 120, dur: 40 }] },
    touch: null,
    derived_features: null,
    ae_recon_error: null,
    ae_model_version: null,
    context: {
      submitted_at: "2026-06-17T12:00:01Z",
      page: "login",
      pre_txn_dwell_ms: 0,
      session_age_s: 0,
      correction_rate: 0,
    },
  };

  it("produces an integrity_sig matching an independently computed HMAC (node:crypto)", async () => {
    const nonce = "test-nonce-001";
    const secret = "change_me_dev_only_super_secret";
    const signed = await signPayload(basePartial, nonce, secret);

    // Independently recompute the expected signature via node:crypto (a different
    // crypto API than the implementation's Web Crypto path) using the same
    // gateway-mirrored formula: key=sha256(secret+nonce), msg=nonce‖canonical‖fp‖ts.
    const canonicalStr = canonical({
      channel: basePartial.channel,
      source: basePartial.source,
      action: { type: basePartial.action.type },
      keystroke: {
        events: basePartial.keystroke!.events.map((e) => ({
          key: e.key,
          down: pyFloat(e.down),
          up: pyFloat(e.up),
        })),
        field_id: basePartial.keystroke!.field_id,
      },
      mouse: basePartial.mouse,
      touch: null,
      derived_features: null,
      ae_recon_error: null,
      ae_model_version: null,
      context: {
        submitted_at: basePartial.context.submitted_at,
        page: basePartial.context.page,
        pre_txn_dwell_ms: pyFloat(basePartial.context.pre_txn_dwell_ms),
        session_age_s: pyFloat(basePartial.context.session_age_s),
        correction_rate: pyFloat(basePartial.context.correction_rate),
      },
    });
    const key = createHash("sha256").update(secret + nonce).digest();
    const msg = nonce + canonicalStr + basePartial.device.fingerprint + signed.ts;
    const expectedSig = createHmac("sha256", key).update(msg).digest("hex");

    expect(signed.integrity_sig).toBe(expectedSig);
  });

  it("binds non-null ae_recon_error/ae_model_version into the signature (mobile_edge path)", async () => {
    const nonce = "test-nonce-ae";
    const secret = "change_me_dev_only_super_secret";
    const mobilePartial: UnsignedPayload = {
      ...basePartial,
      channel: "mobile",
      source: "mobile_edge",
      keystroke: null,
      mouse: null,
      derived_features: { typing_speed: 4 },
      ae_recon_error: 0.0731,
      ae_model_version: "lstm_autoencoder@2026-06-20",
    };
    const signed = await signPayload(mobilePartial, nonce, secret);

    const canonicalStr = canonical({
      channel: mobilePartial.channel,
      source: mobilePartial.source,
      action: { type: mobilePartial.action.type },
      keystroke: null,
      mouse: null,
      touch: null,
      derived_features: { typing_speed: pyFloat(4) },
      ae_recon_error: pyFloat(0.0731),
      ae_model_version: "lstm_autoencoder@2026-06-20",
      context: {
        submitted_at: mobilePartial.context.submitted_at,
        page: mobilePartial.context.page,
        pre_txn_dwell_ms: pyFloat(mobilePartial.context.pre_txn_dwell_ms),
        session_age_s: pyFloat(mobilePartial.context.session_age_s),
        correction_rate: pyFloat(mobilePartial.context.correction_rate),
      },
    });
    const key = createHash("sha256").update(secret + nonce).digest();
    const msg = nonce + canonicalStr + mobilePartial.device.fingerprint + signed.ts;
    const expectedSig = createHmac("sha256", key).update(msg).digest("hex");

    expect(signed.integrity_sig).toBe(expectedSig);
    // A different ae_recon_error must change the signature -- proves the field is
    // actually bound into the HMAC, not silently dropped from the canonical tree.
    const tamperedSig = await signPayload({ ...mobilePartial, ae_recon_error: 0.9 }, nonce, secret);
    expect(tamperedSig.integrity_sig).not.toBe(signed.integrity_sig);
  });

  it("advances seq monotonically and stays monotonic across resetSequence()", async () => {
    const a = await signPayload(basePartial, "n1", "secret");
    const b = await signPayload(basePartial, "n2", "secret");
    expect(b.seq).toBeGreaterThan(a.seq);
    // resetSequence() must NOT move seq backward (the gateway's per-binding floor never
    // resets) -- a fresh nonce cycle still yields a strictly-increasing seq, defeating
    // cross-cycle replay rather than colliding with the stored floor.
    resetSequence();
    const c = await signPayload(basePartial, "n3", "secret");
    expect(c.seq).toBeGreaterThan(b.seq);
  });

  it("sets ts as a valid ISO8601 timestamp", async () => {
    const signed = await signPayload(basePartial, "n", "secret");
    expect(() => new Date(signed.ts).toISOString()).not.toThrow();
  });

  it("produces the same integrity_sig for logically identical payloads with different key insertion order", async () => {
    // Same content as basePartial's device/context/keystroke, but every nested
    // object's keys declared in reverse order — proxy for "Python dict vs JS object
    // built with a different field order" since there's no live Python in this test.
    const reorderedPartial: UnsignedPayload = {
      source: "web_sdk",
      channel: "web",
      context: {
        correction_rate: 0,
        session_age_s: 0,
        pre_txn_dwell_ms: 0,
        page: "login",
        submitted_at: "2026-06-17T12:00:01Z",
      },
      derived_features: null,
      ae_model_version: null,
      ae_recon_error: null,
      touch: null,
      mouse: { clicks: [{ dur: 40, t: 120 }], moves: [{ t: 5, y: 2, x: 1 }] },
      keystroke: {
        field_id: "username",
        // Same event sequence/order as basePartial (array order is meaningful
        // temporal data and must NOT be reordered) — only each event object's own
        // key order differs.
        events: [
          { up: 98, down: 12, key: "x" },
          { up: 305, down: 210, key: "x" },
        ],
      },
      action: { type: "LOGIN" },
      device: {
        is_emulator: false,
        is_rooted: false,
        platform: "web",
        language: "en-IN",
        timezone: "Asia/Kolkata",
        screen: "1920x1080",
        ua: "test-ua",
        fingerprint: "device-abc",
      },
    };

    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-17T12:00:05.000Z"));
    try {
      const nonce = "test-nonce-order";
      const secret = "change_me_dev_only_super_secret";
      const a = await signPayload(basePartial, nonce, secret);
      const b = await signPayload(reorderedPartial, nonce, secret);
      expect(a.ts).toBe(b.ts); // frozen clock — isolates key order as the only variable
      expect(a.integrity_sig).toBe(b.integrity_sig);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("fetchNonce", () => {
  it("GETs {apiBase}/api/v1/auth/nonce and maps expires_at -> expiresAt", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ nonce: "n1", expires_at: "2026-06-17T12:02:00Z" }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchNonce("http://localhost:8000");
    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/api/v1/auth/nonce");
    expect(result).toEqual({ nonce: "n1", expiresAt: "2026-06-17T12:02:00Z" });
  });

  it("throws on a non-OK response", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 500 })));
    await expect(fetchNonce("http://localhost:8000")).rejects.toThrow();
  });
});
