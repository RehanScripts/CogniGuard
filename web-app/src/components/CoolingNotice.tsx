interface CoolingNoticeProps {
  coolingUntil: string;
}

export default function CoolingNotice({ coolingUntil }: CoolingNoticeProps) {
  const until = new Date(coolingUntil);
  return (
    <div className="rounded border border-blue-300 bg-blue-50 p-4 text-blue-800">
      This transfer is on a cooling period until {until.toLocaleString()}. New high-value
      transfers to recently-added payees are held briefly so a coerced or late-night addition
      can't immediately drain funds.
    </div>
  );
}
