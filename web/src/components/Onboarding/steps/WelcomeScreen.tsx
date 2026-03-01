interface Props {
  onNext: () => void;
}

export default function WelcomeScreen({ onNext }: Props) {
  return (
    <div className="space-y-4 text-center">
      <p className="text-xs uppercase tracking-widest text-neutral-500">Step 1</p>
      <h2 className="text-2xl font-semibold text-white">Welcome to Raga-Fusion</h2>
      <p className="text-sm text-neutral-300">
        Generate authentic Indian fusion music in seconds. No musical knowledge needed.
      </p>
      <button
        type="button"
        onClick={onNext}
        className="rounded-xl bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white"
      >
        Get Started
      </button>
    </div>
  );
}
