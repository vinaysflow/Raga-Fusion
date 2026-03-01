import { useEffect, useMemo, useRef, useState } from "react";
import { getSessionId, sendTelemetry } from "../api";

export interface AudioPlayerProps {
  trackId?: string;
  audioUrl: string;
  title: string;
  metadata?: {
    raga?: string;
    duration?: number;
    genre?: string;
  };
  albumArt?: string;
  onDownload?: () => void;
  onShare?: () => void;
  showWaveform?: boolean;
  embedded?: boolean;
}

const fmt = (v: number) => `${Math.floor(v / 60)}:${String(Math.floor(v % 60)).padStart(2, "0")}`;

export default function AudioPlayer({
  trackId,
  audioUrl,
  title,
  metadata,
  onDownload,
  onShare,
  showWaveform = true,
  embedded = true,
}: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const telemetryRef = useRef({ started: false, t30: false, t90: false });
  const sessionId = useMemo(() => getSessionId(), []);
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [current, setCurrent] = useState(0);
  const [volume, setVolume] = useState(() => Number(localStorage.getItem("player_volume") ?? 0.8));

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    el.volume = volume;
  }, [volume]);

  useEffect(() => {
    telemetryRef.current = { started: false, t30: false, t90: false };
  }, [audioUrl, trackId]);

  const progress = duration > 0 ? (current / duration) * 100 : 0;
  const bars = useMemo(() => Array.from({ length: 60 }, (_, i) => i), []);

  return (
    <div className={`${embedded ? "" : "fixed bottom-4 left-4 right-4"} rounded-2xl border border-white/10 bg-white/5 p-4 backdrop-blur-xl`}>
      <audio
        ref={audioRef}
        src={audioUrl}
        onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
        onTimeUpdate={(e) => {
          const time = e.currentTarget.currentTime;
          setCurrent(time);
          if (!trackId) return;
          if (time >= 30 && !telemetryRef.current.t30) {
            telemetryRef.current.t30 = true;
            sendTelemetry({
              track_id: trackId,
              session_id: sessionId,
              event_type: "play_30s",
              timestamp: Date.now() / 1000,
            }).catch(() => {});
          }
          if (time >= 90 && !telemetryRef.current.t90) {
            telemetryRef.current.t90 = true;
            sendTelemetry({
              track_id: trackId,
              session_id: sessionId,
              event_type: "play_90s",
              timestamp: Date.now() / 1000,
            }).catch(() => {});
          }
        }}
        onPlay={() => {
          setPlaying(true);
          if (!trackId || telemetryRef.current.started) return;
          telemetryRef.current.started = true;
          sendTelemetry({
            track_id: trackId,
            session_id: sessionId,
            event_type: "play_started",
            timestamp: Date.now() / 1000,
          }).catch(() => {});
        }}
        onPause={() => setPlaying(false)}
      />

      <div className="flex items-center gap-3">
        <div className="h-14 w-14 rounded-xl bg-gradient-to-br from-indigo-500 to-pink-500" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-white">{title}</p>
          <p className="truncate text-xs text-neutral-400">
            {metadata?.raga ?? "Raga"} • {metadata?.genre ?? "Fusion"} • {fmt(duration || metadata?.duration || 0)}
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            const el = audioRef.current;
            if (!el) return;
            if (el.paused) el.play();
            else el.pause();
          }}
          className="h-12 w-12 rounded-full bg-indigo-500 text-lg text-white"
          aria-label={playing ? "Pause" : "Play"}
        >
          {playing ? "❚❚" : "▶"}
        </button>
      </div>

      {showWaveform && (
        <div className="mt-3 flex h-10 items-end gap-[2px]">
          {bars.map((bar) => {
            const active = (bar / bars.length) * 100 <= progress;
            const h = 20 + ((bar * 17) % 24);
            return (
              <div
                key={bar}
                className={`w-[2px] rounded-t ${active ? "bg-gradient-to-t from-indigo-500 to-pink-500" : "bg-neutral-600"}`}
                style={{ height: `${h}px` }}
              />
            );
          })}
        </div>
      )}

      <div className="mt-3 space-y-2">
        <input
          type="range"
          min={0}
          max={Math.max(duration, 0)}
          step={0.1}
          value={current}
          onChange={(e) => {
            const next = Number(e.target.value);
            setCurrent(next);
            if (audioRef.current) audioRef.current.currentTime = next;
          }}
          className="w-full accent-indigo-500"
          aria-label="Playback position"
        />
        <div className="flex items-center justify-between text-xs text-neutral-400">
          <span>{fmt(current)}</span>
          <span>{fmt(duration)}</span>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between gap-3">
        <div className="hidden items-center gap-2 sm:flex">
          <span className="text-xs text-neutral-400">Vol</span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={volume}
            onChange={(e) => {
              const v = Number(e.target.value);
              setVolume(v);
              localStorage.setItem("player_volume", String(v));
            }}
            className="accent-indigo-500"
            aria-label="Volume"
          />
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className="rounded-lg border border-white/15 px-3 py-1.5 text-xs text-white"
            onClick={() => {
              if (trackId) {
                sendTelemetry({
                  track_id: trackId,
                  session_id: sessionId,
                  event_type: "download_clicked",
                  timestamp: Date.now() / 1000,
                }).catch(() => {});
              }
              onDownload?.();
            }}
          >
            💾 Download
          </button>
          <button
            type="button"
            className="rounded-lg border border-white/15 px-3 py-1.5 text-xs text-white"
            onClick={() => {
              if (trackId) {
                sendTelemetry({
                  track_id: trackId,
                  session_id: sessionId,
                  event_type: "share_clicked",
                  timestamp: Date.now() / 1000,
                }).catch(() => {});
              }
              onShare?.();
            }}
          >
            🔗 Share
          </button>
        </div>
      </div>
    </div>
  );
}
