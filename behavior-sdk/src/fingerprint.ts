import type { DeviceInfo } from "./types.js";

function gatherCanvasHash(): string {
  try {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) return "";
    ctx.textBaseline = "top";
    ctx.font = "14px 'Arial'";
    ctx.fillText("CogniGuard", 2, 2);
    return canvas.toDataURL();
  } catch {
    return "";
  }
}

async function sha256Hex(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** Best-effort root/emulator detection — real device-level checks belong to a future
 * native mobile shell, same deferred-stub status as this project's ASN/GeoIP lookups. */
function detectRooted(): boolean {
  return false;
}

function detectEmulator(): boolean {
  const nav = typeof navigator !== "undefined" ? navigator : undefined;
  return !!nav && /HeadlessChrome/i.test(nav.userAgent ?? "");
}

export async function computeFingerprint(): Promise<DeviceInfo> {
  const nav = typeof navigator !== "undefined" ? navigator : ({ userAgent: "", language: "" } as Navigator);
  const ua = nav.userAgent ?? "";
  const screenSize =
    typeof screen !== "undefined" && screen.width && screen.height ? `${screen.width}x${screen.height}` : "";
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone ?? "";
  const language = nav.language ?? "";
  const canvasHash = gatherCanvasHash();

  const fingerprint = await sha256Hex([ua, screenSize, timezone, language, canvasHash].join("|"));

  return {
    fingerprint,
    ua,
    screen: screenSize,
    timezone,
    language,
    platform: "web",
    is_rooted: detectRooted(),
    is_emulator: detectEmulator(),
  };
}
