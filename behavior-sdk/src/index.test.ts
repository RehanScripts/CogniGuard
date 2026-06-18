import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CogniGuard } from "./index.js";

function keyEvent(type: "keydown" | "keyup", key: string): KeyboardEvent {
  return new KeyboardEvent(type, { key, bubbles: true });
}

describe("CogniGuard.collect", () => {
  let form: HTMLFormElement;
  let username: HTMLInputElement;
  let password: HTMLInputElement;

  beforeEach(() => {
    document.body.innerHTML = "";
    form = document.createElement("form");
    username = document.createElement("input");
    username.id = "username";
    username.type = "text";
    password = document.createElement("input");
    password.id = "password";
    password.type = "password";
    form.appendChild(username);
    form.appendChild(password);
    document.body.appendChild(form);

    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.toString().endsWith("/auth/nonce")) {
          return new Response(JSON.stringify({ nonce: "nonce-1", expires_at: "2026-06-17T12:02:00Z" }), {
            status: 200,
          });
        }
        return new Response("{}", { status: 200 });
      }),
    );

    CogniGuard.resetSequence();
    CogniGuard.init({ apiBase: "http://localhost:8000", signingSecret: "change_me_dev_only_super_secret" });
    CogniGuard.attach(form, { page: "login" });
  });

  afterEach(() => {
    CogniGuard.detach();
    vi.unstubAllGlobals();
  });

  it("returns a structurally valid signed BehaviorPayload", async () => {
    username.dispatchEvent(keyEvent("keydown", "a"));
    username.dispatchEvent(keyEvent("keyup", "a"));
    password.dispatchEvent(keyEvent("keydown", "p"));
    password.dispatchEvent(keyEvent("keyup", "p"));
    document.dispatchEvent(new MouseEvent("mousemove", { clientX: 5, clientY: 5 }));

    const payload = await CogniGuard.collect("LOGIN");

    expect(payload.channel).toBe("web");
    expect(payload.source).toBe("web_sdk");
    expect(payload.nonce).toBe("nonce-1");
    expect(payload.seq).toBeGreaterThan(0);
    expect(() => new Date(payload.ts).toISOString()).not.toThrow();
    expect(payload.integrity_sig).toMatch(/^[0-9a-f]{64}$/);
    expect(payload.device.fingerprint).toMatch(/^[0-9a-f]{64}$/);
    expect(payload.action).toEqual({ type: "LOGIN" });
    expect(payload.context.page).toBe("login");

    // password field's keystroke must never carry the real character
    const keys = payload.keystroke?.events.map((e) => e.key) ?? [];
    expect(keys).toContain("x"); // masked password char
    expect(keys).not.toContain("p");

    expect(payload.mouse?.moves.length).toBeGreaterThan(0);
    expect(payload.touch).toBeNull();
    expect(payload.derived_features).toBeNull();
  });

  it("fetches a fresh nonce and advances seq on every collect() call", async () => {
    const first = await CogniGuard.collect("LOGIN");
    const second = await CogniGuard.collect("LOGIN");
    expect(second.seq).toBeGreaterThan(first.seq);
  });
});
