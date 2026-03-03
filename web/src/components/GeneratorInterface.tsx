import { type RefObject, useEffect, useMemo, useRef, useState } from "react";
import SelectionCard from "./SelectionCard";

export interface GeneratorInterfaceProps {
  prompt: string;
  promptLimit?: number;
  generating?: boolean;
  generationStep?: string;
  ragas: Array<{ id: string; name: string; mood?: string[]; time?: string }>;
  genres: Array<{ id: string; name: string; icon?: string; description?: string }>;
  selectedRaga: string;
  selectedGenres: string[];
  duration: number;
  source: string;
  onPromptChange: (value: string) => void;
  onPickRaga: (value: string) => void;
  onToggleGenre: (value: string) => void;
  onDurationChange: (value: number) => void;
  onSourceChange: (value: string) => void;
  onGenerate: () => void;
}

const formatDuration = (seconds: number) => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
const MIN_DURATION = 30;
const MAX_DURATION = 300;

const PROMPT_SUGGESTIONS = [
  "Romantic lofi for sunset meditation",
  "Serene morning raga with ambient pads",
  "Devotional evening track for calm focus",
  "Cinematic raga fusion for deep study",
  "Minimalist raga texture with soft beats",
];

const SOURCE_OPTIONS = [
  {
    id: "library",
    label: "Real Recording",
    icon: "🎵",
    description: "Phrases extracted from authentic raga performances",
    detail: "Higher authenticity, curated gold-tier phrases from classical recordings. Best for traditional and purist results.",
  },
  {
    id: "generated",
    label: "Synthesized",
    icon: "🔧",
    description: "Algorithmically generated raga-compliant phrases",
    detail: "Broader variety, always available for every raga. Good for experimentation and modern fusion styles.",
  },
];

export default function GeneratorInterface({
  prompt,
  promptLimit = 200,
  generating,
  generationStep,
  ragas,
  genres,
  selectedRaga,
  selectedGenres,
  duration,
  source,
  onPromptChange,
  onPickRaga,
  onToggleGenre,
  onDurationChange,
  onSourceChange,
  onGenerate,
}: GeneratorInterfaceProps) {
  const remaining = useMemo(() => `${prompt.length}/${promptLimit}`, [prompt.length, promptLimit]);
  const [showInspiration, setShowInspiration] = useState(false);
  const [advancedMode, setAdvancedMode] = useState(selectedRaga !== "auto");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const ragaScrollRef = useRef<HTMLDivElement | null>(null);
  const genreScrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!textareaRef.current) return;
    textareaRef.current.style.height = "auto";
    textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
  }, [prompt]);

  const durationPct = useMemo(() => {
    const clamped = Math.min(Math.max(duration, MIN_DURATION), MAX_DURATION);
    return ((clamped - MIN_DURATION) / (MAX_DURATION - MIN_DURATION)) * 100;
  }, [duration]);

  const scrollBy = (ref: RefObject<HTMLDivElement | null>, delta: number) => {
    if (!ref.current) return;
    ref.current.scrollBy({ left: delta, behavior: "smooth" });
  };

  const handleRagaSelect = (id: string) => {
    if (selectedRaga === id) {
      onPickRaga("auto");
      return;
    }
    onPickRaga(id);
    setAdvancedMode(true);
  };

  return (
    <section className="space-y-6 rounded-2xl border border-white/10 bg-white/5 p-4 backdrop-blur-xl">
      <div className="space-y-2">
        <label htmlFor="prompt" className="text-sm text-neutral-300">Describe your vibe</label>
        <textarea
          id="prompt"
          ref={textareaRef}
          value={prompt}
          maxLength={promptLimit}
          onChange={(e) => onPromptChange(e.target.value)}
          rows={2}
          placeholder="Describe your vibe... (e.g., 'Romantic lofi for sunset meditation')"
          className="w-full resize-none rounded-xl border border-white/10 bg-neutral-900/70 p-3 text-sm text-white outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-500/40"
          aria-label="Music prompt input"
          aria-describedby="prompt-count"
        />
        <div className="flex items-center justify-between text-xs text-neutral-400">
          <button
            type="button"
            onClick={() => setShowInspiration((prev) => !prev)}
            className="hover:text-indigo-300"
          >
            Need inspiration? → Try these prompts
          </button>
          <span id="prompt-count">{remaining}</span>
        </div>
        {showInspiration && (
          <div className="rounded-xl border border-white/10 bg-neutral-900/60 p-3 text-xs text-neutral-300">
            <p className="mb-2 text-[11px] uppercase tracking-widest text-neutral-500">Prompt ideas</p>
            <div className="flex flex-wrap gap-2">
              {PROMPT_SUGGESTIONS.map((idea) => (
                <button
                  key={idea}
                  type="button"
                  onClick={() => {
                    onPromptChange(idea);
                    setShowInspiration(false);
                  }}
                  className="rounded-full border border-white/10 px-3 py-1 text-xs text-white/80 hover:border-indigo-400 hover:text-white"
                >
                  {idea}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-sm text-neutral-300">Raga</p>
          <label className="flex items-center gap-2 text-xs text-neutral-400">
            <input
              type="checkbox"
              checked={advancedMode}
              onChange={(e) => {
                const next = e.target.checked;
                setAdvancedMode(next);
                if (!next) onPickRaga("auto");
              }}
              className="accent-indigo-500"
            />
            Advanced mode
          </label>
        </div>
        {!advancedMode ? (
          <div className="rounded-xl border border-white/10 bg-neutral-900/60 px-4 py-3 text-sm text-neutral-200">
            Auto (AI decides the raga for your vibe)
          </div>
        ) : (
          <div className="relative">
            <button
              type="button"
              onClick={() => scrollBy(ragaScrollRef, -220)}
              className="absolute left-0 top-1/2 z-10 hidden -translate-y-1/2 rounded-full bg-black/40 p-2 text-xs text-white sm:block"
            >
              ◀
            </button>
            <div ref={ragaScrollRef} className="flex snap-x gap-3 overflow-x-auto pb-2 pl-8 pr-8">
              <SelectionCard
                type="raga"
                id="auto"
                name="Auto"
                icon="✨"
                metadata={{ mood: ["AI decides"], timeOfDay: "evening", scale: "Adaptive" }}
                selected={selectedRaga === "auto"}
                onSelect={handleRagaSelect}
              />
              {ragas.map((raga) => (
                <SelectionCard
                  key={raga.id}
                  type="raga"
                  id={raga.id}
                  name={raga.name}
                  metadata={{
                    mood: raga.mood ?? [],
                    timeOfDay: (raga.time?.toLowerCase().includes("night") ? "night" : raga.time?.toLowerCase().includes("morning") ? "morning" : "evening"),
                  }}
                  selected={selectedRaga === raga.id}
                  onSelect={handleRagaSelect}
                />
              ))}
            </div>
            <button
              type="button"
              onClick={() => scrollBy(ragaScrollRef, 220)}
              className="absolute right-0 top-1/2 z-10 hidden -translate-y-1/2 rounded-full bg-black/40 p-2 text-xs text-white sm:block"
            >
              ▶
            </button>
          </div>
        )}
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-sm text-neutral-300">Genres (max 2)</p>
          <p className="text-xs text-neutral-400">{selectedGenres.length}/2 selected</p>
        </div>
        <div className="relative">
          <button
            type="button"
            onClick={() => scrollBy(genreScrollRef, -220)}
            className="absolute left-0 top-1/2 z-10 hidden -translate-y-1/2 rounded-full bg-black/40 p-2 text-xs text-white sm:block"
          >
            ◀
          </button>
          <div ref={genreScrollRef} className="flex snap-x gap-3 overflow-x-auto pb-2 pl-8 pr-8">
          {genres.map((genre) => (
            <SelectionCard
              key={genre.id}
              type="genre"
              id={genre.id}
              icon={genre.icon}
              name={genre.name}
              description={genre.description}
              metadata={{ mood: [genre.description ?? ""] }}
              selected={selectedGenres.includes(genre.id)}
              disabled={!selectedGenres.includes(genre.id) && selectedGenres.length >= 2}
              onSelect={onToggleGenre}
            />
          ))}
          </div>
          <button
            type="button"
            onClick={() => scrollBy(genreScrollRef, 220)}
            className="absolute right-0 top-1/2 z-10 hidden -translate-y-1/2 rounded-full bg-black/40 p-2 text-xs text-white sm:block"
          >
            ▶
          </button>
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm text-neutral-300">
          <span>Duration</span>
          <span className="font-mono">{formatDuration(duration)}</span>
        </div>
        <div className="relative">
          <input
            type="range"
            min={MIN_DURATION}
            max={MAX_DURATION}
            step={15}
            value={duration}
            onChange={(e) => onDurationChange(Number(e.target.value))}
            className="relative z-10 w-full accent-indigo-500"
            aria-label="Duration slider"
          />
          <div
            className="pointer-events-none absolute -top-6 z-0 -translate-x-1/2 rounded-md bg-neutral-900 px-2 py-0.5 text-[10px] text-neutral-200"
            style={{ left: `${durationPct}%` }}
          >
            {formatDuration(duration)}
          </div>
        </div>
        <div className="flex justify-between text-[10px] text-neutral-500">
          <span>0:30</span>
          <span>1:00</span>
          <span>2:00</span>
          <span>3:00</span>
          <span>5:00</span>
        </div>
      </div>

      {/* Source selection */}
      <div className="space-y-2">
        <p className="text-sm text-neutral-300">Phrase Source</p>
        <div className="grid grid-cols-2 gap-3">
          {SOURCE_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              onClick={() => onSourceChange(opt.id)}
              className={[
                "relative rounded-xl border p-3 text-left transition-all",
                source === opt.id
                  ? "border-indigo-400 bg-indigo-500/10"
                  : "border-white/10 bg-neutral-900/60 hover:border-white/20",
              ].join(" ")}
            >
              {source === opt.id && (
                <span className="absolute right-2 top-2 text-xs text-indigo-400">Active</span>
              )}
              <span className="text-lg">{opt.icon}</span>
              <p className="mt-1 text-sm font-medium text-white">{opt.label}</p>
              <p className="mt-0.5 text-[11px] text-neutral-400 leading-snug">{opt.description}</p>
              <p className="mt-1 text-[10px] text-neutral-500 leading-snug">{opt.detail}</p>
            </button>
          ))}
        </div>
      </div>

      <div className="sr-only" aria-live="polite">
        {generating ? generationStep : ""}
      </div>
      <button
        type="button"
        onClick={onGenerate}
        disabled={generating || !prompt.trim()}
        className="relative w-full overflow-hidden rounded-xl bg-gradient-to-r from-indigo-500 to-pink-500 py-3 font-semibold text-white transition hover:from-indigo-400 hover:to-pink-400 disabled:opacity-40"
      >
        {generating && (
          <span className="absolute inset-0 animate-pulse bg-gradient-to-r from-white/10 via-white/30 to-white/10" />
        )}
        <span className="relative">
          {generating ? generationStep || "Analyzing vibe... Selecting phrases... Mixing..." : "✨ Generate Music"}
        </span>
      </button>
    </section>
  );
}
