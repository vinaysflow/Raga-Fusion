import { useState } from "react";
import { submitFeedback } from "../api";

interface Props {
  trackId: string;
}

const FEEDBACK_TAGS = [
  { id: "authentic", label: "Authentic" },
  { id: "great_mix", label: "Great Mix" },
  { id: "needs_purity", label: "Needs Purity" },
  { id: "too_repetitive", label: "Repetitive" },
  { id: "creative", label: "Creative" },
  { id: "wrong_mood", label: "Wrong Mood" },
];

const DISMISS_KEY = "rf_feedback_dismissed";

export default function FeedbackPrompt({ trackId }: Props) {
  const [rating, setRating] = useState<number | null>(null);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [comment, setComment] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [dismissed, setDismissed] = useState(() => {
    const raw = sessionStorage.getItem(DISMISS_KEY);
    if (!raw) return false;
    try {
      const dismissed: string[] = JSON.parse(raw);
      return dismissed.includes(trackId);
    } catch {
      return false;
    }
  });

  if (dismissed && !submitted) return null;

  function toggleTag(tag: string) {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
    );
  }

  function dismiss() {
    setDismissed(true);
    try {
      const raw = sessionStorage.getItem(DISMISS_KEY);
      const arr: string[] = raw ? JSON.parse(raw) : [];
      arr.push(trackId);
      sessionStorage.setItem(DISMISS_KEY, JSON.stringify(arr.slice(-50)));
    } catch { /* ignore */ }
  }

  async function handleSubmit() {
    if (rating === null) return;
    try {
      await submitFeedback({
        track_id: trackId,
        rating,
        feedback: comment,
        tags: selectedTags,
      });
      setSubmitted(true);
    } catch {
      /* silent — the feedback is best-effort */
    }
  }

  if (submitted) {
    return (
      <div className="border-t border-neutral-700 px-5 py-3 text-center">
        <p className="text-xs text-green-400">Thanks for your feedback!</p>
      </div>
    );
  }

  return (
    <div className="border-t border-neutral-700 px-5 py-4 space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-neutral-400">Rate this result</p>
        <button
          type="button"
          onClick={dismiss}
          className="text-[10px] text-neutral-600 hover:text-neutral-400"
        >
          Dismiss
        </button>
      </div>

      {/* Star rating */}
      <div className="flex gap-1">
        {[1, 2, 3, 4, 5].map((star) => (
          <button
            key={star}
            type="button"
            onClick={() => setRating(star)}
            className={`text-xl transition-colors ${
              rating !== null && star <= rating
                ? "text-amber-400"
                : "text-neutral-600 hover:text-neutral-400"
            }`}
            aria-label={`Rate ${star} out of 5`}
          >
            ★
          </button>
        ))}
        {rating !== null && (
          <span className="ml-2 text-xs text-neutral-500 self-center">{rating}/5</span>
        )}
      </div>

      {/* Tags */}
      <div className="flex flex-wrap gap-1.5">
        {FEEDBACK_TAGS.map((tag) => (
          <button
            key={tag.id}
            type="button"
            onClick={() => toggleTag(tag.id)}
            className={`rounded-full px-2.5 py-1 text-[11px] transition-all border ${
              selectedTags.includes(tag.id)
                ? "bg-amber-600/20 border-amber-500/40 text-amber-300"
                : "bg-neutral-800 border-neutral-700 text-neutral-500 hover:border-neutral-600"
            }`}
          >
            {tag.label}
          </button>
        ))}
      </div>

      {/* Optional comment */}
      {rating !== null && (
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Any additional thoughts? (optional)"
          rows={2}
          className="w-full resize-none rounded-lg border border-neutral-700 bg-neutral-900/70 px-3 py-2 text-xs text-white outline-none placeholder:text-neutral-600 focus:border-amber-500/50"
        />
      )}

      <button
        type="button"
        onClick={handleSubmit}
        disabled={rating === null}
        className="w-full rounded-lg bg-neutral-700 hover:bg-neutral-600 disabled:opacity-30 disabled:hover:bg-neutral-700 px-4 py-2 text-xs text-white font-medium transition-colors"
      >
        Submit Feedback
      </button>
    </div>
  );
}
