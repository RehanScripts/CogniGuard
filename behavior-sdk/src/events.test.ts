import { describe, expect, it } from "vitest";
import { KeystrokeCapture, MouseCapture, TouchCapture } from "./events.js";

function keyEvent(type: "keydown" | "keyup", key: string): KeyboardEvent {
  return new KeyboardEvent(type, { key, bubbles: true });
}

describe("KeystrokeCapture", () => {
  it("records dwell (up-down) and flight (down[i]-up[i-1]) ordering", async () => {
    const el = document.createElement("input");
    const capture = new KeystrokeCapture(el);

    el.dispatchEvent(keyEvent("keydown", "a"));
    await new Promise((r) => setTimeout(r, 5));
    el.dispatchEvent(keyEvent("keyup", "a"));
    await new Promise((r) => setTimeout(r, 5));
    el.dispatchEvent(keyEvent("keydown", "b"));
    await new Promise((r) => setTimeout(r, 5));
    el.dispatchEvent(keyEvent("keyup", "b"));

    const events = capture.drain();
    expect(events).toHaveLength(2);
    expect(events[0]!.key).toBe("a");
    expect(events[1]!.key).toBe("b");
    // dwell: up >= down for every event
    for (const e of events) {
      expect(e.up).toBeGreaterThanOrEqual(e.down);
    }
    // flight: second key's down strictly after first key's up
    expect(events[1]!.down).toBeGreaterThan(events[0]!.up);
  });

  it("never emits the real character for a secret field, only x / control keys", () => {
    const el = document.createElement("input");
    const capture = new KeystrokeCapture(el, { secret: true, fieldId: "password" });

    el.dispatchEvent(keyEvent("keydown", "p"));
    el.dispatchEvent(keyEvent("keyup", "p"));
    el.dispatchEvent(keyEvent("keydown", "Backspace"));
    el.dispatchEvent(keyEvent("keyup", "Backspace"));
    el.dispatchEvent(keyEvent("keydown", "@"));
    el.dispatchEvent(keyEvent("keyup", "@"));

    const events = capture.drain();
    expect(events.map((e) => e.key)).toEqual(["x", "Backspace", "x"]);
    expect(capture.fieldIdValue()).toBe("password");
  });

  it("drain() clears the buffer", () => {
    const el = document.createElement("input");
    const capture = new KeystrokeCapture(el);
    el.dispatchEvent(keyEvent("keydown", "a"));
    el.dispatchEvent(keyEvent("keyup", "a"));
    expect(capture.drain()).toHaveLength(1);
    expect(capture.drain()).toHaveLength(0);
  });
});

describe("MouseCapture", () => {
  it("buffers moves and paired down/up clicks", () => {
    const capture = new MouseCapture(document);

    document.dispatchEvent(new MouseEvent("mousemove", { clientX: 1, clientY: 2 }));
    document.dispatchEvent(new MouseEvent("mousemove", { clientX: 8, clientY: 9 }));
    document.dispatchEvent(new MouseEvent("mousedown"));
    document.dispatchEvent(new MouseEvent("mouseup"));

    const { moves, clicks } = capture.drain();
    expect(moves).toHaveLength(2);
    expect(moves[0]).toEqual({ x: 1, y: 2, t: expect.any(Number) });
    expect(clicks).toHaveLength(1);
    expect(clicks[0]!.dur).toBeGreaterThanOrEqual(0);
  });
});

describe("TouchCapture", () => {
  function touchEvent(type: "touchstart" | "touchend", points: { clientX: number; clientY: number }[]): Event {
    const e = new Event(type, { bubbles: true });
    Object.assign(e, { touches: points, changedTouches: points });
    return e;
  }

  it("derives one swipe record per start->end gesture", async () => {
    const capture = new TouchCapture(document);

    document.dispatchEvent(touchEvent("touchstart", [{ clientX: 0, clientY: 0 }]));
    await new Promise((r) => setTimeout(r, 5));
    document.dispatchEvent(touchEvent("touchend", [{ clientX: 30, clientY: 40 }]));

    const swipes = capture.drain();
    expect(swipes).toHaveLength(1);
    expect(swipes[0]!.len).toBeCloseTo(50, 0); // hypot(30,40) = 50
    expect(swipes[0]!.dur).toBeGreaterThan(0);
  });
});
