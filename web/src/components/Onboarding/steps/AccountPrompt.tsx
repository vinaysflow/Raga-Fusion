interface Props {
  onDone: () => void;
}

export default function AccountPrompt({ onDone }: Props) {
  return (
    <div className="space-y-4 text-center">
      <h2 className="text-xl font-semibold text-white">Save your tracks forever</h2>
      <p className="text-sm text-neutral-300">Sign up to sync your library across devices.</p>
      <div className="flex justify-center gap-2">
        <button type="button" className="rounded-xl bg-indigo-500 px-4 py-2 text-sm font-semibold text-white">
          Sign Up Free
        </button>
        <button
          type="button"
          onClick={onDone}
          className="rounded-xl border border-white/15 px-4 py-2 text-sm font-semibold text-white"
        >
          Continue as Guest
        </button>
      </div>
    </div>
  );
}
