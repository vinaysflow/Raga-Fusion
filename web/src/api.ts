const BASE = "/api";
const SESSION_KEY = "rf_session_id";

export interface ParsedPrompt {
  raga: string;
  genre: string;
  duration: number;
  source: string;
  ai_parsed?: boolean;
  ai_confidence?: number;
  ai_reasoning?: string;
  intent_tags?: string[];
}

export interface GenerateParams {
  raga: string;
  genre: string;
  duration: number;
  source: string;
  prompt: string;
  intent_tags?: string[];
  recommend?: boolean;
  upload_id?: string;
}

export interface TrackMeta {
  track_id: string;
  filename: string;
  display_name: string;
  raga: string;
  genre: string;
  duration: number;
  requested_duration: number;
  source: string;
  prompt: string;
  created_at: string;
  intent_tags?: string[];
  recommend?: boolean;
  quality_score?: number;
  commercial_ready?: boolean;
  versions?: {
    recommender_version?: string;
    variation_engine_version?: string;
    rules_version?: string;
  };
  artifact_urls?: {
    audio?: string;
    plan?: string;
    trace?: string;
    quality?: string;
  };
}

export interface JobStatus {
  track_id: string;
  status: "processing" | "complete" | "error";
  error?: string;
  metadata?: TrackMeta;
}

export interface StyleInfo {
  bpm: number;
  melody: number;
  drums: number;
  bass: number;
  crackle: boolean;
  description: string;
}

export interface RagaInfo {
  id: string;
  name: string;
  thaat: string;
  mood: string[];
  time: string;
  description: string;
}

export interface QualityCheck {
  metric: string;
  value: number;
  target: string;
  pass: boolean;
}

export interface QualityReport {
  file: string;
  duration: number;
  polish: { checks: QualityCheck[]; passed: number; total: number; score: number };
  authenticity: { checks: QualityCheck[]; passed: number; total: number; score: number; detected_raga?: string };
  overall_score: number;
  commercial_ready: boolean;
}

export interface PlanData {
  raga: string;
  style: string;
  duration: number;
  total_phrases: number;
  avg_authenticity: number;
  avg_recommendation_score: number;
  constraints: { passes: boolean; violations: string[]; score: number };
  explanations: string[];
  ai_explanation?: string;
  phrase_sequence: string[];
}

export interface GenerationTrace {
  trace_version: string;
  created_at: string;
  track_id: string;
  request: Record<string, unknown>;
  versions: Record<string, string>;
  resolved?: Record<string, unknown>;
  artifacts?: Record<string, string>;
  stages: Array<{
    name: string;
    status: "ok" | "error" | "skipped";
    reason?: string;
    summary?: Record<string, unknown>;
  }>;
}

export interface TelemetryEvent {
  track_id: string;
  session_id: string;
  event_type: string;
  timestamp?: number;
  payload?: Record<string, unknown>;
}

export function getSessionId(): string {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = (globalThis.crypto?.randomUUID?.() ?? `sess_${Math.random().toString(36).slice(2, 12)}`);
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

export interface AnalysisResult {
  duration: number;
  raga: { best_match: string; confidence: number; info: Record<string, unknown> };
  raga_candidates: { raga: string; confidence: number }[];
  tonal_center: { sa_note: string; sa_hz: number };
  density: { notes_per_second: number; density_label: string };
  tempo: { estimated_bpm: number };
  intent_tags: string[];
  ai_narration?: string;
  upload_id?: string;
}

export interface VariationSuggestion {
  variation_type: string;
  amount: number;
  description: string;
}

// ── Existing endpoints ──────────────────────────────────────────────

export async function parsePrompt(prompt: string): Promise<ParsedPrompt> {
  const res = await fetch(`${BASE}/parse-prompt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  return res.json();
}

export async function generate(params: GenerateParams): Promise<{ track_id: string; status: string }> {
  const res = await fetch(`${BASE}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  return res.json();
}

export async function getStatus(trackId: string): Promise<JobStatus> {
  const res = await fetch(`${BASE}/status/${trackId}`);
  return res.json();
}

export async function getTracks(): Promise<TrackMeta[]> {
  const res = await fetch(`${BASE}/tracks`);
  return res.json();
}

export async function getStyles(): Promise<Record<string, StyleInfo>> {
  const res = await fetch(`${BASE}/styles`);
  return res.json();
}

export async function getRagas(): Promise<RagaInfo[]> {
  const res = await fetch(`${BASE}/ragas`);
  return res.json();
}

export function audioUrl(trackId: string): string {
  return `${BASE}/tracks/${trackId}/audio`;
}

// ── New intelligence endpoints ──────────────────────────────────────

export async function getAiStatus(): Promise<{ available: boolean }> {
  const res = await fetch(`${BASE}/ai/status`);
  return res.json();
}

export async function analyzeUpload(file: File): Promise<AnalysisResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/analyze`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Analysis failed: ${res.statusText}`);
  return res.json();
}

export async function getQuality(trackId: string): Promise<QualityReport> {
  const res = await fetch(`${BASE}/quality/${trackId}`);
  if (!res.ok) throw new Error("Quality evaluation failed");
  return res.json();
}

export async function getPlan(trackId: string): Promise<PlanData> {
  const res = await fetch(`${BASE}/plan/${trackId}`);
  if (!res.ok) throw new Error("Plan not found");
  return res.json();
}

export async function getTrace(trackId: string): Promise<GenerationTrace> {
  const res = await fetch(`${BASE}/trace/${trackId}`);
  if (!res.ok) throw new Error("Trace not found");
  return res.json();
}

export async function sendTelemetry(event: TelemetryEvent): Promise<{ status: string }> {
  const res = await fetch(`${BASE}/telemetry/event`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(event),
  });
  return res.json();
}

export async function getAiExplanation(raga: string, style: string, duration: number): Promise<{ explanations: string[]; ai_explanation?: string }> {
  const res = await fetch(`${BASE}/ai/explain`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ raga, style, duration }),
  });
  return res.json();
}

export async function getVariationSuggestions(raga: string, style: string): Promise<{ variations: VariationSuggestion[] }> {
  const res = await fetch(`${BASE}/ai/suggest-variations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ raga, style }),
  });
  return res.json();
}
