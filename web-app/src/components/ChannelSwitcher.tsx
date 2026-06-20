import { useState } from "react";

export type Channel = "web" | "mobile";

interface ChannelSwitcherProps {
  onChange?: (channel: Channel) => void;
}

// Visual-only: behavior-sdk's collect() always sends channel:"web" (Phase 10's frozen
// contract hardcodes it in index.ts). This toggle illustrates the product's
// multi-channel story; it does not change what telemetry is actually captured.
export default function ChannelSwitcher({ onChange }: ChannelSwitcherProps) {
  const [channel, setChannel] = useState<Channel>("web");

  function select(next: Channel) {
    setChannel(next);
    onChange?.(next);
  }

  return (
    <div
      className="flex items-center gap-2 text-sm text-gray-500"
      title="Illustrative only -- capture always reports as web in this demo"
    >
      <span>Channel:</span>
      <button
        type="button"
        className={`rounded px-2 py-1 ${channel === "web" ? "bg-blue-600 text-white" : "bg-gray-100"}`}
        onClick={() => select("web")}
      >
        Web
      </button>
      <button
        type="button"
        className={`rounded px-2 py-1 ${channel === "mobile" ? "bg-blue-600 text-white" : "bg-gray-100"}`}
        onClick={() => select("mobile")}
      >
        Mobile
      </button>
    </div>
  );
}
