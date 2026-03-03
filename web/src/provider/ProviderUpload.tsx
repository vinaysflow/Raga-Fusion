import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getProviderUploadStatus, getRagas, uploadProviderRecording, type RagaInfo } from "../api";

const STATUS_STEPS = [
  "Validating file",
  "Detecting raga",
  "Extracting phrases",
  "Scoring authenticity",
  "Comparing to gold",
  "Review ready",
];

export default function ProviderUpload() {
  const navigate = useNavigate();
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [ragas, setRagas] = useState<RagaInfo[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [raga, setRaga] = useState(localStorage.getItem("provider_default_raga") || "yaman");
  const [declaredSa, setDeclaredSa] = useState(localStorage.getItem("provider_declared_sa") || "");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploadId, setUploadId] = useState<string | null>(null);

  useEffect(() => {
    getRagas().then(setRagas).catch(() => {});
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const providerId = useMemo(() => localStorage.getItem("provider_id") || "", []);

  async function handleSubmit() {
    if (!file) return;
    setError(null);
    setStatus("processing");
    try {
      const resp = await uploadProviderRecording(providerId, file, raga, declaredSa || null);
      setUploadId(resp.upload_id);
      pollRef.current = setInterval(async () => {
        try {
          const result = await getProviderUploadStatus(resp.upload_id);
          if (result.status === "complete" || result.status === "review_ready") {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            navigate(`/provider/review/${resp.upload_id}`);
          } else if (result.status === "error") {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setError("Processing failed.");
            setStatus("error");
          }
        } catch {
          /* keep polling */
        }
      }, 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      setStatus("error");
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h2 className="text-xl font-semibold">Upload a Recording</h2>
        <p className="text-sm text-neutral-400">
          Upload a clean WAV/FLAC recording. We will extract phrases and build a review report.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <label className="text-sm text-neutral-300">Raga</label>
          <select
            className="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm"
            value={raga}
            onChange={(e) => setRaga(e.target.value)}
          >
            {ragas.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-sm text-neutral-300">Declared Sa (optional)</label>
          <input
            className="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm"
            value={declaredSa}
            onChange={(e) => setDeclaredSa(e.target.value.toUpperCase())}
            placeholder="C, C#, D, Eb..."
          />
        </div>
      </div>

      <div className="rounded-xl border border-white/10 bg-white/5 p-4 space-y-3">
        <input
          type="file"
          accept=".wav,.flac,.mp3,.m4a,.ogg"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="text-sm"
        />
        <p className="text-xs text-neutral-400">
          Recommended: WAV/FLAC, full-length performance (15+ minutes), minimal background noise.
        </p>
      </div>

      <button
        type="button"
        onClick={handleSubmit}
        className="rounded-full bg-indigo-500 px-4 py-2 text-xs font-semibold text-white disabled:opacity-50"
        disabled={!file || !providerId}
      >
        Start Analysis
      </button>
      {!providerId && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
          Provider profile not found. Please complete onboarding first so we can attach your uploads.
        </div>
      )}

      {status === "processing" && (
        <div className="rounded-lg border border-white/10 bg-white/5 p-4 space-y-2">
          <p className="text-xs text-neutral-300">Processing upload...</p>
          <div className="flex flex-wrap gap-2">
            {STATUS_STEPS.map((s) => (
              <span key={s} className="text-[10px] px-2 py-1 rounded-full bg-white/10 text-neutral-300">
                {s}
              </span>
            ))}
          </div>
          {uploadId && <p className="text-[10px] text-neutral-500">Upload ID: {uploadId}</p>}
        </div>
      )}

      {error && (
        <div className="rounded-lg bg-red-900/30 border border-red-800 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}
    </div>
  );
}
