import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { approveProviderUpload, getProviderUploadReview, type AiReview } from "../api";

export default function ProviderReview() {
  const { uploadId } = useParams();
  const navigate = useNavigate();
  const [review, setReview] = useState<AiReview | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!uploadId) return;
    getProviderUploadReview(uploadId)
      .then((data) => {
        setReview(data);
        setSelected(new Set((data.phrases || []).map((p) => p.phrase_id)));
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Review load failed"));
  }, [uploadId]);

  const arcCoverage = useMemo(() => {
    const counts: Record<string, number> = {};
    review?.phrases?.forEach((p) => {
      const key = p.arc_section || "unknown";
      counts[key] = (counts[key] || 0) + 1;
    });
    return counts;
  }, [review]);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleApprove() {
    if (!uploadId) return;
    await approveProviderUpload(uploadId, Array.from(selected));
    navigate("/provider/dashboard");
  }

  const loading = !error && (!review || (uploadId && review.upload_id !== uploadId));

  if (loading) {
    return <div className="text-sm text-neutral-400">Loading review...</div>;
  }

  if (error) {
    return (
      <div className="rounded-lg bg-red-900/30 border border-red-800 px-3 py-2 text-xs text-red-300">
        {error}
      </div>
    );
  }

  if (!review) return null;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h2 className="text-xl font-semibold">Review Extracted Phrases</h2>
        <p className="text-xs text-neutral-400">
          Raga: {review.raga} · Phrases: {review.phrase_count} · Avg authenticity:{" "}
          {review.avg_authenticity?.toFixed?.(2) ?? review.avg_authenticity}
        </p>
        {review.gold_comparison && (
          <p className="text-xs text-amber-300">
            Gold delta: {(review.gold_comparison as Record<string, unknown>).delta as number}
          </p>
        )}
      </div>

      <div className="rounded-lg border border-white/10 bg-white/5 p-4">
        <h3 className="text-xs uppercase tracking-wider text-neutral-400 mb-2">Arc Coverage</h3>
        <div className="flex flex-wrap gap-2">
          {Object.entries(arcCoverage).map(([section, count]) => (
            <span key={section} className="text-[10px] px-2 py-1 rounded-full bg-white/10 text-neutral-300">
              {section}: {count}
            </span>
          ))}
        </div>
      </div>

      <div className="space-y-3">
        {review.phrases.map((p) => {
          const checked = selected.has(p.phrase_id);
          return (
            <div key={p.phrase_id} className="rounded-lg border border-white/10 bg-white/5 p-3 flex items-start justify-between">
              <div className="space-y-1">
                <p className="text-sm font-medium">{p.phrase_id}</p>
                <p className="text-[11px] text-neutral-400">
                  Notes: {(p.notes_detected || []).slice(0, 6).join(" ")}{" "}
                  {p.arc_section ? `· ${p.arc_section}` : ""}
                </p>
                <p className="text-[11px] text-neutral-500">
                  Authenticity: {p.authenticity_score?.toFixed?.(2) ?? p.authenticity_score}
                </p>
              </div>
              <label className="text-xs flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggle(p.phrase_id)}
                  className="accent-indigo-500"
                />
                Approve
              </label>
            </div>
          );
        })}
      </div>

      <div className="flex items-center justify-between">
        <p className="text-xs text-neutral-400">
          Selected: {selected.size} / {review.phrases.length}
        </p>
        <button
          type="button"
          onClick={handleApprove}
          className="rounded-full bg-indigo-500 px-4 py-2 text-xs font-semibold text-white"
        >
          Approve Selected
        </button>
      </div>
    </div>
  );
}
