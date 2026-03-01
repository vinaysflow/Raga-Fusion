interface Props {
  onNext: () => void;
}

const cards = [
  { icon: "💬", title: "Describe Your Vibe", text: "Type what you're feeling." },
  { icon: "🎵", title: "AI Creates Music", text: "Raga + genre fused intelligently." },
  { icon: "✨", title: "Download & Use", text: "Use your generated track instantly." },
];

export default function ExplainMagic({ onNext }: Props) {
  return (
    <div className="space-y-4">
      <h2 className="text-center text-xl font-semibold text-white">How it works</h2>
      <div className="grid gap-3 sm:grid-cols-3">
        {cards.map((card) => (
          <div key={card.title} className="rounded-xl border border-white/10 bg-white/5 p-3">
            <p className="text-2xl">{card.icon}</p>
            <p className="mt-2 text-sm font-medium text-white">{card.title}</p>
            <p className="text-xs text-neutral-400">{card.text}</p>
          </div>
        ))}
      </div>
      <div className="text-center">
        <button
          type="button"
          onClick={onNext}
          className="rounded-xl bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white"
        >
          Next
        </button>
      </div>
    </div>
  );
}
