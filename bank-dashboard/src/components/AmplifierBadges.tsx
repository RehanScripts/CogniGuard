export interface AmplifierLike {
  code: string;
  multiplier: number;
  detail?: string;
}

interface AmplifierBadgesProps {
  amplifiers: AmplifierLike[];
}

export default function AmplifierBadges({ amplifiers }: AmplifierBadgesProps) {
  if (amplifiers.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {amplifiers.map((amp) => (
        <span
          key={amp.code}
          title={amp.detail}
          className="rounded-full bg-soc-warning-light px-2.5 py-0.5 text-xs font-semibold text-soc-warning"
        >
          {amp.code} ×{amp.multiplier}
        </span>
      ))}
    </div>
  );
}
