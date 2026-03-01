import { useRef, useState } from "react";
import type { ParsedPrompt, AnalysisResult } from "../api";
import { parsePrompt, analyzeUpload } from "../api";

interface Props {
  onParsed: (params: ParsedPrompt) => void;
  onAnalysis?: (result: AnalysisResult) => void;
  disabled?: boolean;
}

export default function PromptInput({ onParsed, onAnalysis, disabled }: Props) {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [aiInfo, setAiInfo] = useState<{ reasoning: string; confidence: number } | null>(null);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadResult, setUploadResult] = useState<AnalysisResult | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim() || disabled) return;
    setLoading(true);
    setAiInfo(null);
    try {
      const data = await parsePrompt(text);
      onParsed(data);
      if (data.ai_parsed && data.ai_reasoning) {
        setAiInfo({ reasoning: data.ai_reasoning, confidence: data.ai_confidence ?? 0 });
      }
    } catch {
      /* user can fill form manually */
    } finally {
      setLoading(false);
    }
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadLoading(true);
    setUploadResult(null);
    setAiInfo(null);
    try {
      const result = await analyzeUpload(file);
      setUploadResult(result);
      onAnalysis?.(result);
      const raga = result.raga?.best_match ?? "yaman";
      onParsed({
        raga,
        genre: "lofi",
        duration: 120,
        source: "generated",
        ai_parsed: true,
        ai_confidence: result.raga?.confidence ?? 0,
        ai_reasoning: result.ai_narration ?? `Detected raga: ${raga}`,
        intent_tags: result.intent_tags ?? [],
      });
      if (result.ai_narration) {
        setAiInfo({
          reasoning: result.ai_narration,
          confidence: result.raga?.confidence ?? 0,
        });
      }
    } catch {
      /* upload failed */
    } finally {
      setUploadLoading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div className="w-full space-y-3">
      <form onSubmit={handleSubmit}>
        <label className="block text-sm text-neutral-400 mb-2">
          Describe your vibe — or upload a song
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Haunting midnight track with electronic beats..."
            disabled={disabled}
            className="flex-1 rounded-lg bg-neutral-800 border border-neutral-700 px-4 py-3 text-white placeholder-neutral-500 focus:outline-none focus:border-amber-500 transition-colors"
          />
          <button
            type="submit"
            disabled={disabled || loading || !text.trim()}
            className="rounded-lg bg-amber-600 hover:bg-amber-500 px-5 py-3 text-sm font-medium text-white disabled:opacity-40 transition-colors"
          >
            {loading ? "Thinking..." : "Parse"}
          </button>
        </div>
      </form>

      <div className="flex items-center gap-3">
        <div className="h-px flex-1 bg-neutral-800" />
        <span className="text-xs text-neutral-600 uppercase tracking-widest">or</span>
        <div className="h-px flex-1 bg-neutral-800" />
      </div>

      <div>
        <input
          ref={fileRef}
          type="file"
          accept=".mp3,.wav,.flac,.ogg,.m4a"
          onChange={handleFileUpload}
          disabled={disabled || uploadLoading}
          className="hidden"
          id="song-upload"
        />
        <label
          htmlFor="song-upload"
          className={`flex items-center justify-center gap-2 w-full rounded-lg border-2 border-dashed px-4 py-3 text-sm cursor-pointer transition-colors ${
            uploadLoading
              ? "border-amber-600 text-amber-400 bg-amber-900/10"
              : "border-neutral-700 text-neutral-500 hover:border-amber-600 hover:text-amber-400 hover:bg-amber-900/5"
          } ${disabled ? "opacity-40 pointer-events-none" : ""}`}
        >
          {uploadLoading ? (
            <>
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
              Analyzing your song...
            </>
          ) : (
            <>
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
              Upload a song to find the best fusion
            </>
          )}
        </label>
      </div>

      {aiInfo && (
        <div className="rounded-lg bg-amber-900/15 border border-amber-800/30 px-4 py-3 space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-amber-400">AI Intelligence</span>
            <span className="text-xs text-amber-600">
              {Math.round(aiInfo.confidence * 100)}% confident
            </span>
          </div>
          <p className="text-sm text-amber-200/80 leading-relaxed">{aiInfo.reasoning}</p>
        </div>
      )}

      {uploadResult && !uploadResult.ai_narration && (
        <div className="rounded-lg bg-neutral-800/60 border border-neutral-700 px-4 py-3 text-sm text-neutral-400">
          Detected: <span className="text-white font-medium">{uploadResult.raga?.best_match}</span>
          {" "}&middot; {uploadResult.density?.density_label} density
          {" "}&middot; ~{uploadResult.tempo?.estimated_bpm} BPM
        </div>
      )}
    </div>
  );
}
