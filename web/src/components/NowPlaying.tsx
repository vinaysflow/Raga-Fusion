import { useEffect, useState } from "react";
import {
  type TrackMeta, type QualityReport, type PlanData,
  type VariationSuggestion,
  audioUrl, getQuality, getPlan, getVariationSuggestions,
} from "../api";

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

  useEffect(() => {
    setQuality(null);
    setPlan(null);
    setVariations([]);
    setTab("about");
  }, [track.track_id]);

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

  return (
    <div className="w-full rounded-xl bg-neutral-800/60 border border-neutral-700 overflow-hidden">
      {/* Header */}
      <div className="p-5 pb-4">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-lg font-semibold text-white">{track.display_name}</h3>
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

        <audio controls src={url} className="w-full mt-4" />

        {track.prompt && (
          <p className="text-xs text-neutral-500 italic mt-2">Prompt: "{track.prompt}"</p>
        )}
      </div>

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


function QualityTab({ report, loading }: { report: QualityReport | null; loading: boolean }) {
  if (loading) return <p className="text-sm text-neutral-500 animate-pulse">Evaluating quality...</p>;
  if (!report) return <p className="text-sm text-neutral-600">Click to load quality metrics</p>;

  const overallPct = Math.round(report.overall_score * 100);

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


function PlanTab({ plan, loading }: { plan: PlanData | null; loading: boolean }) {
  if (loading) return <p className="text-sm text-neutral-500 animate-pulse">Loading plan...</p>;
  if (!plan) return <p className="text-sm text-neutral-600">No plan available for this track</p>;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 text-sm">
        <span className="text-neutral-400">{plan.total_phrases} phrases</span>
        <span className="text-neutral-600">&middot;</span>
        <span className="text-neutral-400">Auth: {Math.round(plan.avg_authenticity * 100)}%</span>
        <span className="text-neutral-600">&middot;</span>
        <span className={plan.constraints.passes ? "text-green-500" : "text-amber-400"}>
          {plan.constraints.passes ? "Constraints met" : `${plan.constraints.violations.length} issue(s)`}
        </span>
      </div>

      {plan.constraints.violations.length > 0 && (
        <div className="space-y-1">
          {plan.constraints.violations.map((v, i) => (
            <p key={i} className="text-xs text-amber-400/80 pl-3 border-l-2 border-amber-600/30">{v}</p>
          ))}
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
