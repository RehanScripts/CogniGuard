import { describe, expect, it } from "vitest";
import { computeFingerprint } from "./fingerprint.js";

describe("computeFingerprint", () => {
  it("returns a full DeviceInfo shape with a deterministic hex fingerprint", async () => {
    const info = await computeFingerprint();
    expect(info.fingerprint).toMatch(/^[0-9a-f]{64}$/);
    expect(info.platform).toBe("web");
    expect(typeof info.ua).toBe("string");
    expect(typeof info.timezone).toBe("string");
    expect(info.is_rooted).toBe(false);
    expect(typeof info.is_emulator).toBe("boolean");
  });

  it("is stable across calls in the same environment", async () => {
    const a = await computeFingerprint();
    const b = await computeFingerprint();
    expect(a.fingerprint).toBe(b.fingerprint);
  });
});
