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
          className="rounded-full bg-purple-100 px-2 py-0.5 text-xs text-purple-800"
        >
          {amp.code} ×{amp.multiplier}
        </span>
      ))}
    </div>
  );
}
