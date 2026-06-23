interface CoercionCheckProps {
  amount: number;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function CoercionCheck({ amount, onConfirm, onCancel }: CoercionCheckProps) {
  return (
    <div className="rounded border border-cbi-accent bg-red-50 p-4">
      <p className="font-medium text-cbi-accent-dark">
        You're sending ₹{amount.toLocaleString("en-IN")} to a payee added a short while ago.
      </p>
      <p className="mt-1 text-sm text-cbi-accent-dark">Is someone instructing you to do this right now?</p>
      <div className="mt-3 flex gap-2">
        <button type="button" className="rounded bg-cbi-accent px-3 py-1 text-white hover:bg-cbi-accent-dark" onClick={onCancel}>
          Cancel -- I'm being told what to do
        </button>
        <button
          type="button"
          className="rounded border border-cbi-accent px-3 py-1 text-cbi-accent-dark"
          onClick={onConfirm}
        >
          No, this is genuinely me
        </button>
      </div>
    </div>
  );
}
