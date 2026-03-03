import { type TrackMeta } from "../api";

interface Props {
  tracks: TrackMeta[];
  currentId?: string;
  onSelect: (track: TrackMeta) => void;
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

const tierBadge: Record<string, { label: string; cls: string }> = {
  gold: { label: "Gold", cls: "bg-yellow-500/20 text-yellow-300 border-yellow-500/30" },
  standard: { label: "Std", cls: "bg-blue-500/20 text-blue-300 border-blue-500/30" },
  generated: { label: "Synth", cls: "bg-neutral-500/20 text-neutral-400 border-neutral-500/30" },
  blended: { label: "Blend", cls: "bg-purple-500/20 text-purple-300 border-purple-500/30" },
};

export default function TrackHistory({ tracks, currentId, onSelect }: Props) {
  if (tracks.length === 0) {
    return (
      <div className="text-center py-8 text-neutral-600 text-sm">
        No tracks generated yet. Create your first one above!
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {tracks.filter((t) => t.track_id).map((t, i) => {
        const tier = t.library_tier ?? t.actual_source ?? t.source;
        const badge = tierBadge[tier];
        return (
          <button
            key={t.track_id ?? i}
            onClick={() => onSelect(t)}
            className={`w-full text-left rounded-lg px-4 py-3 transition-colors ${
              t.track_id === currentId
                ? "bg-amber-600/20 border border-amber-600/40"
                : "bg-neutral-800/40 border border-neutral-800 hover:bg-neutral-800"
            }`}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-sm font-medium text-white truncate">
                  {(t.raga ?? "unknown").charAt(0).toUpperCase() + (t.raga ?? "unknown").slice(1)} &middot;{" "}
                  {(t.genre ?? "unknown").replace(/_/g, " ").charAt(0).toUpperCase() + (t.genre ?? "unknown").replace(/_/g, " ").slice(1)}
                </span>
                {badge && (
                  <span className={`shrink-0 rounded-full border px-1.5 py-0.5 text-[9px] font-medium ${badge.cls}`}>
                    {badge.label}
                  </span>
                )}
                {t.quality_score !== undefined && (
                  <span className={`shrink-0 text-[10px] font-mono ${
                    t.commercial_ready ? "text-green-400" : "text-amber-400"
                  }`}>
                    {Math.round(t.quality_score * 100)}%
                  </span>
                )}
              </div>
              <span className="text-xs text-neutral-500 shrink-0 ml-2">
                {t.created_at ? timeAgo(t.created_at) : ""}
              </span>
            </div>
            {t.prompt && (
              <p className="text-xs text-neutral-500 mt-1 truncate">"{t.prompt}"</p>
            )}
          </button>
        );
      })}
    </div>
  );
}
