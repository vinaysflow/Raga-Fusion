import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getProviderDashboard, type ProviderDashboard } from "../api";

export default function ProviderDashboard() {
  const providerId = localStorage.getItem("provider_id");
  const [data, setData] = useState<ProviderDashboard | null>(null);
  const [error, setError] = useState<string | null>(() =>
    providerId ? null : "Provider not found. Please register first.",
  );

  useEffect(() => {
    if (!providerId) {
      return;
    }
    getProviderDashboard(providerId)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Dashboard load failed"));
  }, [providerId]);

  if (error) {
    return (
      <div className="rounded-lg bg-red-900/30 border border-red-800 px-3 py-2 text-xs text-red-300">
        {error}
      </div>
    );
  }

  if (!data) {
    return <div className="text-sm text-neutral-400">Loading dashboard...</div>;
  }

  const { provider, uploads, stats } = data;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">{provider.name}</h2>
          <p className="text-xs text-neutral-400">
            {provider.gharana || "Independent"} · {provider.status || "pending"}
          </p>
        </div>
        <Link
          to="/provider/upload"
          className="rounded-full bg-indigo-500 px-4 py-2 text-xs font-semibold text-white"
        >
          Upload New Recording
        </Link>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-lg border border-white/10 bg-white/5 p-4">
          <p className="text-xs text-neutral-400">Uploads</p>
          <p className="text-lg font-semibold">{stats.total_uploads}</p>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/5 p-4">
          <p className="text-xs text-neutral-400">Approved phrases</p>
          <p className="text-lg font-semibold">{stats.phrases_approved}</p>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/5 p-4">
          <p className="text-xs text-neutral-400">Ragas covered</p>
          <p className="text-sm font-semibold">{stats.ragas_covered.join(", ") || "—"}</p>
        </div>
      </div>

      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-neutral-300">Upload History</h3>
        <div className="space-y-2">
          {uploads.length === 0 && (
            <p className="text-xs text-neutral-400">No uploads yet.</p>
          )}
          {uploads.map((upload) => (
            <div key={upload.upload_id} className="rounded-lg border border-white/10 bg-white/5 p-3 flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">{upload.raga}</p>
                <p className="text-[11px] text-neutral-500">
                  Phrases: {upload.phrase_count ?? 0} · Approved: {upload.phrases_approved ?? 0}
                </p>
              </div>
              <Link
                to={`/provider/review/${upload.upload_id}`}
                className="text-xs text-indigo-300 hover:text-indigo-200"
              >
                View Review
              </Link>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
