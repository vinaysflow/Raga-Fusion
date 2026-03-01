import { useEffect, useState } from "react";

export interface UserPreferences {
  generation: {
    defaultRaga: string | "auto";
    defaultGenres: string[];
    defaultDuration: number;
    audioQuality: "standard" | "high" | "lossless";
    fadeInOut: number;
  };
  playback: {
    defaultVolume: number;
    autoPlay: boolean;
    showWaveform: boolean;
    enableKeyboardShortcuts: boolean;
  };
  display: {
    showEducationalPanel: boolean;
    showTechnicalDetails: boolean;
  };
  appearance: {
    theme: "light" | "dark" | "auto";
    accentColor: string;
    reducedMotion: boolean;
    highContrast: boolean;
    fontSize: "small" | "medium" | "large";
  };
  privacy: {
    allowAnalytics: boolean;
    emailNotifications: boolean;
  };
}

const KEY = "user_preferences_v1";
const defaultPrefs: UserPreferences = {
  generation: { defaultRaga: "auto", defaultGenres: ["lofi"], defaultDuration: 120, audioQuality: "high", fadeInOut: 1 },
  playback: { defaultVolume: 80, autoPlay: false, showWaveform: true, enableKeyboardShortcuts: true },
  display: { showEducationalPanel: true, showTechnicalDetails: false },
  appearance: { theme: "dark", accentColor: "#6366F1", reducedMotion: false, highContrast: false, fontSize: "medium" },
  privacy: { allowAnalytics: true, emailNotifications: false },
};

interface Props {
  open: boolean;
  onClose: () => void;
  onChange?: (prefs: UserPreferences) => void;
}

export default function SettingsPanel({ open, onClose, onChange }: Props) {
  const [prefs, setPrefs] = useState<UserPreferences>(defaultPrefs);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(KEY);
      if (raw) setPrefs(JSON.parse(raw));
    } catch {
      // no-op
    }
  }, []);

  useEffect(() => {
    localStorage.setItem(KEY, JSON.stringify(prefs));
    onChange?.(prefs);
  }, [prefs, onChange]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/50" onClick={onClose}>
      <aside
        className="absolute right-0 top-0 h-full w-full max-w-md overflow-y-auto border-l border-white/10 bg-neutral-950 p-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Settings</h2>
          <button type="button" onClick={onClose} className="text-neutral-300">✕</button>
        </div>

        <section className="space-y-3">
          <h3 className="text-xs uppercase tracking-widest text-neutral-500">Generation</h3>
          <label className="block text-sm text-neutral-300">
            Default duration: {prefs.generation.defaultDuration}s
            <input
              type="range"
              min={30}
              max={300}
              step={15}
              value={prefs.generation.defaultDuration}
              onChange={(e) =>
                setPrefs((p) => ({ ...p, generation: { ...p.generation, defaultDuration: Number(e.target.value) } }))
              }
              className="mt-1 w-full accent-indigo-500"
            />
          </label>

          <label className="flex items-center justify-between text-sm text-neutral-300">
            Show waveform
            <input
              type="checkbox"
              checked={prefs.playback.showWaveform}
              onChange={(e) =>
                setPrefs((p) => ({ ...p, playback: { ...p.playback, showWaveform: e.target.checked } }))
              }
              className="accent-indigo-500"
            />
          </label>

          <label className="flex items-center justify-between text-sm text-neutral-300">
            Allow analytics
            <input
              type="checkbox"
              checked={prefs.privacy.allowAnalytics}
              onChange={(e) =>
                setPrefs((p) => ({ ...p, privacy: { ...p.privacy, allowAnalytics: e.target.checked } }))
              }
              className="accent-indigo-500"
            />
          </label>
        </section>

        <div className="mt-6 flex gap-2">
          <button
            type="button"
            onClick={() => setPrefs(defaultPrefs)}
            className="rounded-lg border border-white/15 px-3 py-2 text-sm text-white"
          >
            Reset to defaults
          </button>
          <button type="button" onClick={onClose} className="rounded-lg bg-indigo-500 px-3 py-2 text-sm text-white">
            Done
          </button>
        </div>
      </aside>
    </div>
  );
}
