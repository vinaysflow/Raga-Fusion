interface Props {
  onNext: () => void;
}

export default function InteractiveDemo({ onNext }: Props) {
  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-white">Interactive demo</h2>
      <div className="grid gap-4 sm:grid-cols-3">
        <ol className="space-y-2 rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-neutral-300 sm:col-span-1">
          <li>1. Describe your vibe</li>
          <li>2. Keep Ambient selected</li>
          <li>3. Set duration to 1:00</li>
          <li>4. Press Generate</li>
        </ol>
        <div className="rounded-xl border border-white/10 bg-neutral-900/70 p-3 text-xs text-neutral-400 sm:col-span-2">
          Generator preview panel connects here.
        </div>
      </div>
      <button
        type="button"
        onClick={onNext}
        className="rounded-xl bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white"
      >
        Continue
      </button>
    </div>
  );
}
