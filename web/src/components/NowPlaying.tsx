import { useState } from "react";
import {
  type TrackMeta, type QualityReport, type PlanData,
  type VariationSuggestion, type QualityCheck,
  audioUrl, getQuality, getPlan, getVariationSuggestions,
} from "../api";
import FeedbackPrompt from "./FeedbackPrompt";

interface Props {
  track: TrackMeta;
}

type Tab = "about" | "quality" | "plan" | "variations";

function formatDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function cap(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function NowPlaying({ track }: Props) {
  const [tab, setTab] = useState<Tab>("about");
  const [quality, setQuality] = useState<QualityReport | null>(null);
  const [qualityLoading, setQualityLoading] = useState(false);
  const [plan, setPlan] = useState<PlanData | null>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [variations, setVariations] = useState<VariationSuggestion[]>([]);
  const [varLoading, setVarLoading] = useState(false);
  const url = audioUrl(track.track_id);

  function loadQuality() {
    if (quality || qualityLoading) return;
    setQualityLoading(true);
    getQuality(track.track_id)
      .then(setQuality)
      .catch(() => {})
      .finally(() => setQualityLoading(false));
  }

  function loadPlan() {
    if (plan || planLoading) return;
    setPlanLoading(true);
    getPlan(track.track_id)
      .then(setPlan)
      .catch(() => {})
      .finally(() => setPlanLoading(false));
  }

  function loadVariations() {
    if (variations.length > 0 || varLoading) return;
    setVarLoading(true);
    getVariationSuggestions(track.raga, track.genre)
      .then((r) => setVariations(r.variations || []))
      .catch(() => {})
      .finally(() => setVarLoading(false));
  }

  function handleTabChange(t: Tab) {
    setTab(t);
    if (t === "quality") loadQuality();
    if (t === "plan") loadPlan();
    if (t === "variations") loadVariations();
  }

  const tabs: { id: Tab; label: string }[] = [
    { id: "about", label: "About" },
    { id: "quality", label: "Quality" },
    { id: "plan", label: "Plan" },
    { id: "variations", label: "Variations" },
  ];

  const tierColors: Record<string, string> = {
    gold: "bg-yellow-500/20 text-yellow-300 border-yellow-500/30",
    standard: "bg-blue-500/20 text-blue-300 border-blue-500/30",
    generated: "bg-neutral-500/20 text-neutral-300 border-neutral-500/30",
    blended: "bg-purple-500/20 text-purple-300 border-purple-500/30",
  };
  const tier = track.library_tier ?? track.actual_source ?? track.source;
  const tierLabel = tier === "gold" ? "Gold Library" : tier === "standard" ? "Standard Library" : tier === "generated" ? "Synthesized" : tier === "blended" ? "Blended" : cap(tier);

  return (
    <div className="w-full rounded-xl bg-neutral-800/60 border border-neutral-700 overflow-hidden">
      {/* Header */}
      <div className="p-5 pb-4">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-semibold text-white">{track.display_name}</h3>
              <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${tierColors[tier] ?? tierColors.generated}`}>
                {tierLabel}
              </span>
            </div>
            <p className="text-sm text-neutral-400 mt-1">
              {cap(track.raga)} &middot; {cap(track.genre)} &middot; {formatDuration(track.duration)}
            </p>
          </div>
          <a
            href={url}
            download={`${track.display_name}.wav`}
            className="rounded-lg bg-neutral-700 hover:bg-neutral-600 px-4 py-2 text-sm text-neutral-300 transition-colors shrink-0"
          >
            Download
          </a>
        </div>

        {/* Inline quality summary */}
        {quality && (
          <div className="mt-3 flex items-center gap-3 rounded-lg bg-neutral-900/50 px-3 py-2">
            <span className={`text-sm font-bold ${quality.commercial_ready ? "text-green-400" : "text-amber-400"}`}>
              {Math.round(quality.overall_score * 100)}%
            </span>
            <span className="text-xs text-neutral-500">
              Polish {quality.polish.passed}/{quality.polish.total} &middot; Authenticity {quality.authenticity.passed}/{quality.authenticity.total}
            </span>
            {quality.commercial_ready
              ? <span className="ml-auto text-[10px] text-green-400">Commercial Ready</span>
              : <span className="ml-auto text-[10px] text-amber-400">Needs Polish</span>}
          </div>
        )}
        {qualityLoading && !quality && (
          <div className="mt-3 flex items-center gap-2 rounded-lg bg-neutral-900/50 px-3 py-2">
            <span className="text-xs text-neutral-500 animate-pulse">Evaluating quality...</span>
          </div>
        )}

        <audio controls src={url} className="w-full mt-4" />

        {track.prompt && (
          <p className="text-xs text-neutral-500 italic mt-2">Prompt: "{track.prompt}"</p>
        )}
      </div>

      {/* Feedback prompt */}
      <FeedbackPrompt trackId={track.track_id} />

      {/* Tab bar */}
      <div className="flex border-t border-neutral-700">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => handleTabChange(t.id)}
            className={`flex-1 px-4 py-2.5 text-xs font-medium transition-colors ${
              tab === t.id
                ? "text-amber-400 border-b-2 border-amber-500 bg-neutral-800/50"
                : "text-neutral-500 hover:text-neutral-400 border-b-2 border-transparent"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="p-5 pt-4">
        {tab === "about" && <AboutTab raga={track.raga} />}
        {tab === "quality" && <QualityTab report={quality} loading={qualityLoading} />}
        {tab === "plan" && <PlanTab plan={plan} loading={planLoading} />}
        {tab === "variations" && <VariationsTab variations={variations} loading={varLoading} raga={track.raga} style={track.genre} />}
      </div>
    </div>
  );
}


function AboutTab({ raga }: { raga: string }) {
  const blurbs: Record<string, string> = {
    yaman: "Raga Yaman is one of the most fundamental ragas in Hindustani music. Performed in the early evening (6-9 PM), it evokes serenity, devotion, and quiet joy. Its raised 4th (tivra Ma) gives it a distinctive brightness — the Western equivalent is the Lydian mode.",
    bhairavi: "Raga Bhairavi uses all flat notes and creates a deeply emotional, devotional mood. Traditionally performed at dawn or as the concluding raga of a concert. The Western equivalent is the Phrygian mode.",
    bhairav: "Raga Bhairav is a morning raga of great majesty and seriousness. Its combination of flat Re and flat Dha with natural Ga and Ni creates a distinctive tension. Named after Lord Shiva.",
    malkauns: "Raga Malkauns is a pentatonic late-night raga of profound depth and mystery. It omits Re and Pa entirely, creating an introspective, haunting mood perfect for deep contemplation.",
    desh: "Raga Desh is a light, romantic raga associated with the monsoon season. It has a playful, joyful character and is often used in semi-classical and film music.",
  };
  const text = blurbs[raga] || `This track uses Raga ${cap(raga)}.`;
  return (
    <div className="rounded-lg bg-neutral-900/50 p-4">
      <p className="text-xs font-medium text-amber-400 mb-2">About this raga</p>
      <p className="text-sm text-neutral-400 leading-relaxed">{text}</p>
    </div>
  );
}


function hintForCheck(check: QualityCheck): string | null {
  if (check.pass) return null;
  const m = check.metric.toLowerCase();
  if (m.includes("lufs")) return "Try a different style or increase duration for better loudness balance.";
  if (m.includes("noise") || m.includes("floor")) return "Switch to the Real Recording source for cleaner audio.";
  if (m.includes("peak")) return "Reduce duration or try a calmer style to avoid clipping.";
  if (m.includes("dynamic")) return "A longer duration allows better dynamic expression.";
  if (m.includes("pakad")) return "Switch to Real Recording (Gold) for stronger pakad presence.";
  if (m.includes("forbidden")) return "Use a Gold library or switch ragas — some phrase sources have off-scale notes.";
  if (m.includes("vadi")) return "Enable AI Recommendation for better vadi emphasis.";
  if (m.includes("scale")) return "Switch to Real Recording source for purer scale compliance.";
  return "Try adjusting source, duration, or style for better results.";
}

function QualityTab({ report, loading }: { report: QualityReport | null; loading: boolean }) {
  if (loading) return <p className="text-sm text-neutral-500 animate-pulse">Evaluating quality...</p>;
  if (!report) return <p className="text-sm text-neutral-600">Quality data not yet available</p>;

  const overallPct = Math.round(report.overall_score * 100);
  const failedChecks = [
    ...report.polish.checks.filter((c) => !c.pass),
    ...report.authenticity.checks.filter((c) => !c.pass),
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <div className={`text-3xl font-bold ${report.commercial_ready ? "text-green-400" : "text-amber-400"}`}>
          {overallPct}%
        </div>
        <div>
          <p className={`text-sm font-medium ${report.commercial_ready ? "text-green-400" : "text-amber-400"}`}>
            {report.commercial_ready ? "Commercial Ready" : "Needs Polish"}
          </p>
          <p className="text-xs text-neutral-500">
            Polish: {report.polish.passed}/{report.polish.total} &middot;
            Auth: {report.authenticity.passed}/{report.authenticity.total}
          </p>
        </div>
      </div>

      {failedChecks.length > 0 && (
        <div className="rounded-lg border border-amber-800/30 bg-amber-900/10 p-3 space-y-1.5">
          <p className="text-[11px] font-medium text-amber-400 uppercase tracking-wider">Suggestions</p>
          {failedChecks.slice(0, 3).map((c, i) => {
            const hint = hintForCheck(c);
            return hint ? (
              <p key={i} className="text-xs text-amber-200/70 pl-2 border-l-2 border-amber-600/30">
                <span className="text-amber-400">{c.metric}:</span> {hint}
              </p>
            ) : null;
          })}
        </div>
      )}

      <div className="space-y-1">
        <p className="text-xs font-medium text-neutral-400 mb-2">Production Polish</p>
        {report.polish.checks.map((c, i) => (
          <div key={i} className="flex items-center justify-between text-xs py-1">
            <span className="text-neutral-500">{c.metric}</span>
            <div className="flex items-center gap-2">
              <span className="text-neutral-400 font-mono">{typeof c.value === "number" ? c.value.toFixed(1) : c.value}</span>
              <span className={`w-5 text-center ${c.pass ? "text-green-500" : "text-red-400"}`}>
                {c.pass ? "✓" : "✗"}
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="space-y-1">
        <p className="text-xs font-medium text-neutral-400 mb-2">Raga Authenticity</p>
        {report.authenticity.checks.map((c, i) => (
          <div key={i} className="flex items-center justify-between text-xs py-1">
            <span className="text-neutral-500">{c.metric}</span>
            <div className="flex items-center gap-2">
              <span className="text-neutral-400 font-mono">{typeof c.value === "number" ? c.value.toFixed(3) : c.value}</span>
              <span className={`w-5 text-center ${c.pass ? "text-green-500" : "text-red-400"}`}>
                {c.pass ? "✓" : "✗"}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}


function violationHint(violation: string): string {
  const v = violation.toLowerCase();
  if (v.includes("pakad")) return "Consider switching to Gold library or a different raga with richer recordings.";
  if (v.includes("vadi")) return "Try enabling AI Recommendation or use a library source with more authentic phrases.";
  if (v.includes("forbidden")) return "The phrase library may contain off-scale notes. Try Gold library or re-extract with stricter filters.";
  if (v.includes("diversity") || v.includes("unique")) return "Increase duration or use a raga with a larger phrase library.";
  return "";
}

function PlanTab({ plan, loading }: { plan: PlanData | null; loading: boolean }) {
  if (loading) return <p className="text-sm text-neutral-500 animate-pulse">Loading plan...</p>;
  if (!plan) return <p className="text-sm text-neutral-600">No plan available for this track</p>;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 text-sm flex-wrap">
        <span className="text-neutral-400">{plan.total_phrases} phrases</span>
        <span className="text-neutral-600">&middot;</span>
        <span className="text-neutral-400">Auth: {Math.round(plan.avg_authenticity * 100)}%</span>
        <span className="text-neutral-600">&middot;</span>
        <span className="text-neutral-400">Score: {Math.round(plan.avg_recommendation_score * 100)}%</span>
        <span className="text-neutral-600">&middot;</span>
        <span className={plan.constraints.passes ? "text-green-500" : "text-amber-400"}>
          {plan.constraints.passes ? "All constraints met" : `${plan.constraints.violations.length} issue(s)`}
        </span>
      </div>

      {plan.constraints.violations.length > 0 && (
        <div className="rounded-lg border border-amber-800/30 bg-amber-900/10 p-3 space-y-2">
          <p className="text-[11px] font-medium text-amber-400 uppercase tracking-wider">Constraint Issues</p>
          {plan.constraints.violations.map((v, i) => {
            const hint = violationHint(v);
            return (
              <div key={i} className="pl-2 border-l-2 border-amber-600/30">
                <p className="text-xs text-amber-400/80">{v}</p>
                {hint && <p className="text-[11px] text-neutral-500 mt-0.5">{hint}</p>}
              </div>
            );
          })}
        </div>
      )}

      {plan.ai_explanation && (
        <div className="rounded-lg bg-amber-900/10 border border-amber-800/20 p-4">
          <p className="text-xs font-medium text-amber-400 mb-2">AI Analysis</p>
          <p className="text-sm text-amber-200/70 leading-relaxed whitespace-pre-line">{plan.ai_explanation}</p>
        </div>
      )}

      {!plan.ai_explanation && plan.explanations.length > 0 && (
        <div className="space-y-1">
          {plan.explanations.map((e, i) => (
            <p key={i} className="text-xs text-neutral-400 pl-3 border-l-2 border-neutral-700">{e}</p>
          ))}
        </div>
      )}
    </div>
  );
}


function VariationsTab({ variations, loading, raga, style }: { variations: VariationSuggestion[]; loading: boolean; raga: string; style: string }) {
  if (loading) return <p className="text-sm text-neutral-500 animate-pulse">Getting AI suggestions...</p>;
  if (variations.length === 0) return <p className="text-sm text-neutral-600">No variation suggestions available</p>;

  return (
    <div className="space-y-3">
      <p className="text-xs text-neutral-500">AI-suggested variations for {cap(raga)} + {cap(style)}</p>
      {variations.map((v, i) => (
        <div key={i} className="rounded-lg bg-neutral-900/50 p-3 space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-amber-400">{cap(v.variation_type)}</span>
            <span className="text-xs text-neutral-600">amount: {v.amount}</span>
          </div>
          <p className="text-sm text-neutral-400">{v.description}</p>
        </div>
      ))}
    </div>
  );
}
