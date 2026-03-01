interface Props {
  onNext: () => void;
}

export default function FirstSuccess({ onNext }: Props) {
  return (
    <div className="space-y-4 text-center">
      <h2 className="text-2xl font-semibold text-white">You made your first track</h2>
      <p className="text-sm text-neutral-300">
        Press play, inspect waveform, and open the learning panel to understand the raga fusion.
      </p>
      <button
        type="button"
        onClick={onNext}
        className="rounded-xl bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white"
      >
        Start Creating
      </button>
    </div>
  );
}
