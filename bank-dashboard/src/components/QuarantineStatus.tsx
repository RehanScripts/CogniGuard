interface QuarantineStatusProps {
  quarantinedSamples: number;
}

export default function QuarantineStatus({ quarantinedSamples }: QuarantineStatusProps) {
  const hasQuarantined = quarantinedSamples > 0;
  return (
    <div className={`rounded-xl border p-4 text-sm ${hasQuarantined ? "border-band-medium-bg bg-band-medium-bg" : "border-soc-border bg-soc-elevated"}`}>
      <p className={`font-semibold ${hasQuarantined ? "text-band-medium" : "text-soc-text"}`}>
        {quarantinedSamples} quarantined sample{quarantinedSamples === 1 ? "" : "s"}
      </p>
      <p className="mt-0.5 text-xs text-soc-muted">
        Step-up-passed telemetry held back from training, pending a clean 7-day cooling window.
      </p>
    </div>
  );
}
