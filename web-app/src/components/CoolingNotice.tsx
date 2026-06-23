interface CoolingNoticeProps {
  coolingUntil: string;
}

export default function CoolingNotice({ coolingUntil }: CoolingNoticeProps) {
  const until = new Date(coolingUntil);
  return (
    <div className="rounded border border-cbi-primary-light bg-cbi-primary-light p-4 text-cbi-primary-dark">
      This transfer is on a cooling period until {until.toLocaleString()}. New high-value
      transfers to recently-added payees are held briefly so a coerced or late-night addition
      can't immediately drain funds.
    </div>
  );
}
