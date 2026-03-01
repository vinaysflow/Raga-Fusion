import { useCallback, useEffect, useRef, useState } from "react";
import {
  audioUrl,
  generate,
  getSessionId,
  getAiStatus,
  getRagas,
  getStatus,
  getTracks,
  sendTelemetry,
  type TrackMeta,
} from "./api";
import NowPlaying from "./components/NowPlaying";
import TrackHistory from "./components/TrackHistory";
import Spinner from "./components/Spinner";
import GeneratorInterface from "./components/GeneratorInterface";
import AudioPlayer from "./components/AudioPlayer";
import SettingsPanel, { type UserPreferences } from "./components/SettingsPanel";
import OnboardingFlow from "./components/Onboarding/OnboardingFlow";

export default function App() {
  const [raga, setRaga] = useState("auto");
  const [duration, setDuration] = useState(120);
  const [source] = useState("library");
  const [prompt, setPrompt] = useState("");
  const [recommend] = useState(true);
  const [intentTags] = useState<string[]>([]);
  const [selectedGenres, setSelectedGenres] = useState<string[]>(["lofi"]);
  const [ragas, setRagas] = useState<Array<{ id: string; name: string; mood?: string[]; time?: string }>>([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(
    () => localStorage.getItem("onboarding_completed") !== "true",
  );
  const [generationStep, setGenerationStep] = useState("Analyzing vibe...");

  const [generating, setGenerating] = useState(false);
  const [currentTrack, setCurrentTrack] = useState<TrackMeta | null>(null);
  const [tracks, setTracks] = useState<TrackMeta[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [aiAvailable, setAiAvailable] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refreshTracks = useCallback(() => {
    getTracks().then(setTracks).catch(() => {});
  }, []);

  useEffect(() => {
    refreshTracks();
    getAiStatus().then((s) => setAiAvailable(s.available)).catch(() => {});
    getRagas().then((list) => setRagas(list)).catch(() => {});
  }, [refreshTracks]);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const genreCards = [
    { id: "lofi", name: "Lofi", icon: "🎧", description: "Chill beats" },
    { id: "ambient", name: "Ambient", icon: "🧘", description: "Spacious and calm" },
    { id: "jazz_fusion", name: "Jazz", icon: "🎹", description: "Rich harmony" },
    { id: "upbeat", name: "Upbeat", icon: "🔥", description: "Energetic pulse" },
  ];

  async function handleGenerate() {
    const sessionId = getSessionId();
    setGenerating(true);
    setError(null);
    if (currentTrack?.track_id) {
      sendTelemetry({
        track_id: currentTrack.track_id,
        session_id: sessionId,
        event_type: "regenerate_clicked",
        timestamp: Date.now() / 1000,
      }).catch(() => {});
    }
    setCurrentTrack(null);
    const promptText = prompt;
    const primaryGenre = selectedGenres[0] ?? "lofi";
    setGenerationStep("Analyzing vibe...");

    try {
      setGenerationStep("Selecting phrases...");
      const { track_id } = await generate({
        raga: raga === "auto" ? "yaman" : raga,
        genre: primaryGenre,
        duration,
        source,
        prompt: promptText,
        intent_tags: intentTags,
        recommend,
      });
      setGenerationStep("Mixing...");
      sendTelemetry({
        track_id,
        session_id: sessionId,
        event_type: "generate_clicked",
        timestamp: Date.now() / 1000,
      }).catch(() => {});

      pollRef.current = setInterval(async () => {
        try {
          const status = await getStatus(track_id);
          if (status.status === "complete" && status.metadata) {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setCurrentTrack(status.metadata);
            setGenerating(false);
            setGenerationStep("Done");
            refreshTracks();
          } else if (status.status === "error") {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setError(status.error || "Generation failed");
            setGenerating(false);
          }
        } catch {
          /* keep polling */
        }
      }, 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
      setGenerating(false);
    }
  }

  function handleToggleGenre(nextGenre: string) {
    setSelectedGenres((prev) => {
      if (prev.includes(nextGenre)) {
        return prev.filter((g) => g !== nextGenre);
      }
      if (prev.length >= 2) return prev;
      return [...prev, nextGenre];
    });
  }

  function handleSettingsChange(prefs: UserPreferences) {
    setDuration(prefs.generation.defaultDuration);
    setSelectedGenres(prefs.generation.defaultGenres.slice(0, 2));
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#0A0A0F] to-[#1A1A2E] text-white">
      <div className="max-w-2xl mx-auto px-4 py-10 space-y-8">
        {/* Header */}
        <header className="text-center space-y-2">
          <h1 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-amber-400 to-orange-400 bg-clip-text text-transparent">
            Raga-Fusion Music Generator
          </h1>
          <p className="text-neutral-500 text-sm">
            Indian classical raga meets modern production
            {aiAvailable && (
              <span className="ml-2 inline-flex items-center gap-1 text-amber-500/60 text-xs">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                AI Active
              </span>
            )}
          </p>
          <button
            type="button"
            onClick={() => setSettingsOpen(true)}
            className="mt-2 text-xs text-neutral-400 hover:text-neutral-200"
          >
            ⚙️ Settings
          </button>
        </header>

        {showOnboarding && (
          <OnboardingFlow onFinish={() => setShowOnboarding(false)} />
        )}

        {!showOnboarding && (
          <GeneratorInterface
            prompt={prompt}
            generating={generating}
            generationStep={generationStep}
            ragas={ragas}
            genres={genreCards}
            selectedRaga={raga}
            selectedGenres={selectedGenres}
            duration={duration}
            onPromptChange={setPrompt}
            onPickRaga={setRaga}
            onToggleGenre={handleToggleGenre}
            onDurationChange={setDuration}
            onGenerate={handleGenerate}
          />
        )}

        {/* Status */}
        {generating && (
          <Spinner label="Generating your fusion track... this can take 10-30 seconds" />
        )}
        {error && (
          <div className="rounded-lg bg-red-900/30 border border-red-800 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {/* Now Playing */}
        {currentTrack && (
          <div className="space-y-3">
            <AudioPlayer
              trackId={currentTrack.track_id}
              audioUrl={audioUrl(currentTrack.track_id)}
              title={currentTrack.display_name}
              metadata={{
                raga: currentTrack.raga,
                genre: currentTrack.genre,
                duration: currentTrack.duration,
              }}
              onDownload={() => window.open(audioUrl(currentTrack.track_id), "_blank")}
              onShare={() => navigator.clipboard?.writeText(window.location.href)}
            />
            <NowPlaying track={currentTrack} />
          </div>
        )}

        {/* Track History */}
        {tracks.length > 0 && (
          <section className="space-y-3">
            <h2 className="text-sm font-semibold text-neutral-500 uppercase tracking-wider">
              Previous Tracks
            </h2>
            <TrackHistory
              tracks={tracks}
              currentId={currentTrack?.track_id}
              onSelect={setCurrentTrack}
            />
          </section>
        )}
      </div>
      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} onChange={handleSettingsChange} />
    </div>
  );
}
