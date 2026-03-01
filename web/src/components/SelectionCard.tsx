import { useEffect, useMemo, useRef } from "react";

export interface SelectionCardProps {
  type: "raga" | "genre";
  id: string;
  name: string;
  icon?: string;
  description?: string;
  metadata: {
    timeOfDay?: "morning" | "afternoon" | "evening" | "night";
    mood?: string[];
    scale?: string;
    color?: string;
  };
  selected: boolean;
  disabled?: boolean;
  onSelect: (id: string) => void;
  previewUrl?: string;
}

const timeIcon: Record<string, string> = {
  morning: "🌄",
  afternoon: "☀️",
  evening: "🌅",
  night: "🌙",
};

export default function SelectionCard({
  type,
  id,
  name,
  icon,
  description,
  metadata,
  selected,
  disabled,
  onSelect,
  previewUrl,
}: SelectionCardProps) {
  const gradient = useMemo(() => {
    const base = metadata.color ?? "#6366F1";
    return `linear-gradient(135deg, ${base}55 0%, #EC489955 100%)`;
  }, [metadata.color]);
  const previewRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    return () => {
      if (previewRef.current) {
        previewRef.current.pause();
        previewRef.current = null;
      }
    };
  }, []);

  return (
    <button
      type="button"
      onClick={() => onSelect(id)}
      onMouseEnter={() => {
        if (!previewUrl || disabled) return;
        if (!previewRef.current) {
          previewRef.current = new Audio(previewUrl);
          previewRef.current.volume = 0.4;
        }
        previewRef.current.currentTime = 0;
        previewRef.current.play().catch(() => {});
      }}
      onMouseLeave={() => {
        if (previewRef.current) {
          previewRef.current.pause();
        }
      }}
      disabled={disabled}
      aria-pressed={selected}
      aria-label={`${type} ${name}`}
      className={[
        "relative h-[180px] w-[140px] shrink-0 snap-start overflow-hidden rounded-2xl border text-left transition-all",
        "bg-white/5 backdrop-blur-md",
        selected
          ? "border-indigo-400 bg-indigo-500/10 shadow-[0_0_28px_rgba(99,102,241,0.35)]"
          : "border-white/15 hover:-translate-y-1 hover:scale-[1.02] hover:border-white/30 hover:shadow-lg",
        disabled ? "cursor-not-allowed opacity-40" : "cursor-pointer",
      ].join(" ")}
    >
      {selected && (
        <span className="absolute right-2 top-2 rounded-full bg-indigo-500 px-1.5 py-0.5 text-xs text-white transition">
          ✓
        </span>
      )}

      <div className="h-[60px] p-2" style={{ background: gradient }}>
        <div className="text-2xl">{icon ?? (type === "genre" ? "🎵" : "🎼")}</div>
      </div>

      <div className="space-y-1 px-3 py-2">
        <p className="truncate text-base font-semibold text-white">{name}</p>
        {type === "raga" ? (
          <>
            <p className="text-xs text-neutral-300">
              {metadata.timeOfDay ? `${timeIcon[metadata.timeOfDay]} ${metadata.timeOfDay}` : "Auto"}
            </p>
            <p className="truncate font-mono text-[10px] text-neutral-400">{metadata.scale ?? "S R G m P D N"}</p>
          </>
        ) : (
          <>
            <p className="truncate text-xs text-neutral-300">{description ?? "Fusion style"}</p>
            <p className="truncate text-[10px] text-neutral-500">{metadata.mood?.slice(0, 2).join(", ") || "Modern vibe"}</p>
          </>
        )}
      </div>

      {type === "raga" && metadata.mood?.length ? (
        <div className="flex gap-1 px-3 pb-2">
          {metadata.mood.slice(0, 2).map((tag) => (
            <span key={tag} className="truncate rounded-full bg-white/10 px-2 py-0.5 text-[10px] text-neutral-200">
              {tag}
            </span>
          ))}
        </div>
      ) : null}
    </button>
  );
}
