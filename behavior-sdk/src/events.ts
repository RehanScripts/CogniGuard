import type { KeyEvent, MouseClick, MouseMove, TouchSwipe } from "./types.js";

/** Single-character keys are masked to "x" on secret fields — multi-character key
 * names (Backspace, Shift, Enter, ArrowLeft, ...) never reveal the typed character,
 * so they're tracked as-is even on secret fields. */
function maskKey(key: string, secret: boolean): string {
  if (secret && key.length === 1) return "x";
  return key;
}

export class KeystrokeCapture {
  private buffer: KeyEvent[] = [];
  private downAt = new Map<string, number>();
  private readonly startedAt: number;
  private readonly secret: boolean;
  private readonly fieldId: string;
  private readonly target: EventTarget;
  private readonly onKeyDown = (e: Event): void => this.handleKeyDown(e as KeyboardEvent);
  private readonly onKeyUp = (e: Event): void => this.handleKeyUp(e as KeyboardEvent);

  constructor(target: EventTarget, opts: { fieldId?: string; secret?: boolean; clockOrigin?: number } = {}) {
    this.target = target;
    this.fieldId = opts.fieldId ?? "";
    this.secret = opts.secret ?? false;
    this.startedAt = opts.clockOrigin ?? performance.now();
    target.addEventListener("keydown", this.onKeyDown);
    target.addEventListener("keyup", this.onKeyUp);
  }

  private now(): number {
    return performance.now() - this.startedAt;
  }

  private handleKeyDown(e: KeyboardEvent): void {
    // Repeated keydown (held key) before keyup: keep the first down timestamp.
    if (!this.downAt.has(e.key)) {
      this.downAt.set(e.key, this.now());
    }
  }

  private handleKeyUp(e: KeyboardEvent): void {
    const masked = maskKey(e.key, this.secret);
    const down = this.downAt.get(e.key);
    this.downAt.delete(e.key);
    const up = this.now();
    this.buffer.push({ key: masked, down: down ?? up, up });
  }

  fieldIdValue(): string {
    return this.fieldId;
  }

  drain(): KeyEvent[] {
    const events = this.buffer;
    this.buffer = [];
    return events;
  }

  destroy(): void {
    this.target.removeEventListener("keydown", this.onKeyDown);
    this.target.removeEventListener("keyup", this.onKeyUp);
  }
}

export class MouseCapture {
  private moveBuffer: MouseMove[] = [];
  private clickBuffer: MouseClick[] = [];
  private downAt: number | null = null;
  private readonly startedAt: number;
  private readonly target: EventTarget;
  private readonly onMove = (e: Event): void => this.handleMove(e as MouseEvent);
  private readonly onDown = (): void => this.handleDown();
  private readonly onUp = (): void => this.handleUp();

  constructor(target: EventTarget, clockOrigin?: number) {
    this.target = target;
    this.startedAt = clockOrigin ?? performance.now();
    target.addEventListener("mousemove", this.onMove);
    target.addEventListener("mousedown", this.onDown);
    target.addEventListener("mouseup", this.onUp);
  }

  private now(): number {
    return performance.now() - this.startedAt;
  }

  private handleMove(e: MouseEvent): void {
    this.moveBuffer.push({ x: e.clientX, y: e.clientY, t: this.now() });
  }

  private handleDown(): void {
    this.downAt = this.now();
  }

  private handleUp(): void {
    const t = this.now();
    const dur = this.downAt === null ? 0 : t - this.downAt;
    this.downAt = null;
    this.clickBuffer.push({ t, dur });
  }

  drain(): { moves: MouseMove[]; clicks: MouseClick[] } {
    const moves = this.moveBuffer;
    const clicks = this.clickBuffer;
    this.moveBuffer = [];
    this.clickBuffer = [];
    return { moves, clicks };
  }

  destroy(): void {
    this.target.removeEventListener("mousemove", this.onMove);
    this.target.removeEventListener("mousedown", this.onDown);
    this.target.removeEventListener("mouseup", this.onUp);
  }
}

interface TouchPoint {
  clientX: number;
  clientY: number;
}

interface TouchLikeEvent {
  touches: ArrayLike<TouchPoint>;
  changedTouches: ArrayLike<TouchPoint>;
}

export class TouchCapture {
  private buffer: TouchSwipe[] = [];
  private start: { x: number; y: number; t: number } | null = null;
  private readonly startedAt: number;
  private readonly target: EventTarget;
  private readonly onStart = (e: Event): void => this.handleStart(e as unknown as TouchLikeEvent);
  private readonly onEnd = (e: Event): void => this.handleEnd(e as unknown as TouchLikeEvent);

  constructor(target: EventTarget, clockOrigin?: number) {
    this.target = target;
    this.startedAt = clockOrigin ?? performance.now();
    target.addEventListener("touchstart", this.onStart);
    target.addEventListener("touchend", this.onEnd);
  }

  private now(): number {
    return performance.now() - this.startedAt;
  }

  private handleStart(e: TouchLikeEvent): void {
    const touch = e.touches[0];
    if (!touch) return;
    this.start = { x: touch.clientX, y: touch.clientY, t: this.now() };
  }

  private handleEnd(e: TouchLikeEvent): void {
    if (!this.start) return;
    const touch = e.changedTouches[0];
    const t = this.now();
    const dur = t - this.start.t;
    if (touch && dur > 0) {
      const dx = touch.clientX - this.start.x;
      const dy = touch.clientY - this.start.y;
      this.buffer.push({
        len: Math.hypot(dx, dy),
        dur,
        vx: dx / dur,
        vy: dy / dur,
      });
    }
    this.start = null;
  }

  drain(): TouchSwipe[] {
    const swipes = this.buffer;
    this.buffer = [];
    return swipes;
  }

  destroy(): void {
    this.target.removeEventListener("touchstart", this.onStart);
    this.target.removeEventListener("touchend", this.onEnd);
  }
}
