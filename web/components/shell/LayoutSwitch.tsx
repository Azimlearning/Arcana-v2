// The Basic | Adaptive control. Basic is the fixed starting layout; Adaptive is the one composed for the current answer
// and exists only after an answer. Choosing Basic pins it (a later adaptive layout no longer takes over by itself);
// choosing Adaptive un-pins it. Both buttons state their pressed state, and Adaptive says why it is unavailable.

import type { LayoutChoice } from "@/lib/store";

export function LayoutSwitch({
  choice,
  adaptiveAvailable,
  onChoose,
}: {
  choice: LayoutChoice;
  adaptiveAvailable: boolean;
  onChoose: (choice: LayoutChoice) => void;
}) {
  const button = (value: LayoutChoice, label: string, disabled = false) => (
    <button
      type="button"
      aria-pressed={choice === value}
      disabled={disabled}
      aria-describedby={disabled ? "adaptive-hint" : undefined}
      onClick={() => onChoose(value)}
      className={`px-3 py-1 text-sm first:rounded-l-md last:rounded-r-md border border-stone-300 disabled:opacity-40 ${
        choice === value ? "bg-stone-900 text-white" : "bg-white text-stone-700 hover:bg-stone-100"
      }`}
    >
      {label}
    </button>
  );
  return (
    <div className="flex items-center gap-2">
      <div role="group" aria-label="Layout" className="flex">
        {button("basic", "Basic")}
        {button("adaptive", "Adaptive", !adaptiveAvailable)}
      </div>
      {!adaptiveAvailable && (
        <span id="adaptive-hint" className="text-xs text-stone-500">
          Adaptive is available after your first answer.
        </span>
      )}
    </div>
  );
}
