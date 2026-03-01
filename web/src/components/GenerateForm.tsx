import { useEffect, useState } from "react";
import { getRagas, getStyles, type RagaInfo, type StyleInfo } from "../api";

interface Props {
  raga: string;
  genre: string;
  duration: number;
  source: string;
  recommend: boolean;
  intentTags: string[];
  onRagaChange: (v: string) => void;
  onGenreChange: (v: string) => void;
  onDurationChange: (v: number) => void;
  onSourceChange: (v: string) => void;
  onRecommendChange: (v: boolean) => void;
  onIntentTagsChange: (v: string[]) => void;
  onGenerate: () => void;
  disabled?: boolean;
}

const INTENT_OPTIONS = [
  { id: "meditative", label: "Meditative", icon: "🧘" },
  { id: "energetic", label: "Energetic", icon: "⚡" },
  { id: "calm", label: "Calm", icon: "🌊" },
  { id: "intense", label: "Intense", icon: "🔥" },
  { id: "dense", label: "Complex", icon: "🎼" },
  { id: "minimal", label: "Minimal", icon: "✨" },
];

export default function GenerateForm({
  raga, genre, duration, source, recommend, intentTags,
  onRagaChange, onGenreChange, onDurationChange, onSourceChange,
  onRecommendChange, onIntentTagsChange,
  onGenerate, disabled,
}: Props) {
  const [ragas, setRagas] = useState<RagaInfo[]>([]);
  const [styles, setStyles] = useState<Record<string, StyleInfo>>({});

  useEffect(() => {
    getRagas().then(setRagas).catch(() => {});
    getStyles().then(setStyles).catch(() => {});
  }, []);

  const styleKeys = Object.keys(styles);
  const selectedRaga = ragas.find((r) => r.id === raga);

  function toggleIntent(tag: string) {
    if (intentTags.includes(tag)) {
      onIntentTagsChange(intentTags.filter((t) => t !== tag));
    } else {
      onIntentTagsChange([...intentTags, tag]);
    }
  }

  return (
    <div className="w-full space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div>
          <label className="block text-xs text-neutral-500 mb-1">Raga</label>
          <select
            value={raga}
            onChange={(e) => onRagaChange(e.target.value)}
            disabled={disabled}
            className="w-full rounded-lg bg-neutral-800 border border-neutral-700 px-3 py-2.5 text-white text-sm focus:outline-none focus:border-amber-500 transition-colors"
          >
            {ragas.length > 0
              ? ragas.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)
              : <option value="yaman">Yaman</option>}
          </select>
        </div>
        <div>
          <label className="block text-xs text-neutral-500 mb-1">Style</label>
          <select
            value={genre}
            onChange={(e) => onGenreChange(e.target.value)}
            disabled={disabled}
            className="w-full rounded-lg bg-neutral-800 border border-neutral-700 px-3 py-2.5 text-white text-sm focus:outline-none focus:border-amber-500 transition-colors"
          >
            {styleKeys.length > 0
              ? styleKeys.map((s) => (
                  <option key={s} value={s}>{s.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}</option>
                ))
              : ["lofi", "ambient", "calm", "upbeat"].map((s) => (
                  <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
                ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-neutral-500 mb-1">Source</label>
          <select
            value={source}
            onChange={(e) => onSourceChange(e.target.value)}
            disabled={disabled}
            className="w-full rounded-lg bg-neutral-800 border border-neutral-700 px-3 py-2.5 text-white text-sm focus:outline-none focus:border-amber-500 transition-colors"
          >
            <option value="library">Real Recording</option>
            <option value="generated">Synthesized</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-neutral-500 mb-1">
            Duration: {Math.floor(duration / 60)}:{String(duration % 60).padStart(2, "0")}
          </label>
          <input
            type="range"
            min={15} max={180} step={15}
            value={duration}
            onChange={(e) => onDurationChange(Number(e.target.value))}
            disabled={disabled}
            className="w-full accent-amber-500 mt-2"
          />
        </div>
      </div>

      {selectedRaga && (
        <div className="flex items-center gap-2 text-xs text-neutral-500">
          <span className="text-amber-500/60">{selectedRaga.thaat} thaat</span>
          <span>&middot;</span>
          <span>{selectedRaga.time || "any time"}</span>
          {selectedRaga.mood?.length > 0 && (
            <>
              <span>&middot;</span>
              <span>{selectedRaga.mood.slice(0, 2).join(", ")}</span>
            </>
          )}
        </div>
      )}

      <div>
        <label className="block text-xs text-neutral-500 mb-2">Intent (optional)</label>
        <div className="flex flex-wrap gap-2">
          {INTENT_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              onClick={() => toggleIntent(opt.id)}
              disabled={disabled}
              className={`rounded-full px-3 py-1.5 text-xs font-medium transition-all ${
                intentTags.includes(opt.id)
                  ? "bg-amber-600/20 border border-amber-500/40 text-amber-300"
                  : "bg-neutral-800 border border-neutral-700 text-neutral-500 hover:border-neutral-600 hover:text-neutral-400"
              }`}
            >
              {opt.icon} {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <label className="flex items-center gap-2 cursor-pointer group">
          <input
            type="checkbox"
            checked={recommend}
            onChange={(e) => onRecommendChange(e.target.checked)}
            disabled={disabled}
            className="w-4 h-4 accent-amber-500 rounded"
          />
          <span className="text-sm text-neutral-400 group-hover:text-neutral-300 transition-colors">
            AI Recommendation Engine
          </span>
        </label>
        <span className="text-xs text-neutral-600">
          {recommend ? "Phrases ranked by raga authenticity + style fit" : "Standard phrase selection"}
        </span>
      </div>

      <button
        onClick={onGenerate}
        disabled={disabled}
        className="w-full rounded-lg bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 disabled:from-neutral-700 disabled:to-neutral-700 disabled:text-neutral-500 px-6 py-3.5 text-white font-semibold text-lg transition-all shadow-lg shadow-amber-900/20 hover:shadow-amber-900/30"
      >
        {disabled ? "Generating..." : "Generate Fusion Track"}
      </button>
    </div>
  );
}
