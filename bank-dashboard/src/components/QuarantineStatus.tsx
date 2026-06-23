interface QuarantineStatusProps {
  quarantinedSamples: number;
}

export default function QuarantineStatus({ quarantinedSamples }: QuarantineStatusProps) {
  return (
    <div className="rounded-lg border bg-white p-3 text-sm shadow-sm">
      <p className="font-medium">
        {quarantinedSamples} quarantined sample{quarantinedSamples === 1 ? "" : "s"}
      </p>
      <p className="text-gray-500">
        Step-up-passed telemetry held back from training, pending a clean 7-day cooling window.
      </p>
    </div>
  );
}
