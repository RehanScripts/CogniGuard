import { useState } from "react";

interface ManualAmountEntryProps {
  expectedAmount: number;
  onConfirmed: (amount: number) => void;
}

// Forces the customer to *type* the amount rather than tap-confirm a pre-filled value
// -- defeats remote-control auto-fill and captures a fresh behavioral sample at the
// decisive moment (PRD §10.3).
export default function ManualAmountEntry({ expectedAmount, onConfirmed }: ManualAmountEntryProps) {
  const [value, setValue] = useState("");
  const matches = Number(value) === expectedAmount && value !== "";

  return (
    <div className="rounded border border-amber-300 bg-amber-50 p-4">
      <p className="font-medium text-amber-800">Please re-type the amount to confirm this transfer.</p>
      <input
        type="number"
        className="mt-2 w-full rounded border px-2 py-1"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={`₹${expectedAmount}`}
      />
      <button
        type="button"
        disabled={!matches}
        className="mt-2 rounded bg-amber-600 px-3 py-1 text-white disabled:opacity-50"
        onClick={() => onConfirmed(Number(value))}
      >
        Confirm amount
      </button>
    </div>
  );
}
