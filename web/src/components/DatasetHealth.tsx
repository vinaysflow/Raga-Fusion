import { useState } from "react";
import { getDatasetHealth, type DatasetHealth as DatasetHealthType, type LibraryInfo } from "../api";

function cap(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const tierColors: Record<string, string> = {
  gold: "text-yellow-300",
  standard: "text-blue-300",
  generated: "text-neutral-400",
};

export default function DatasetHealth() {
  const [data, setData] = useState<DatasetHealthType | null>(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  const handleToggle = () => {
    setOpen((prev) => {
      const next = !prev;
      if (next && !data) {
        setLoading(true);
        getDatasetHealth()
          .then(setData)
          .catch(() => {})
          .finally(() => setLoading(false));
      }
      return next;
    });
  };

  return (
    <section className="space-y-2">
      <button
        type="button"
        onClick={handleToggle}
        className="flex items-center gap-2 text-sm font-semibold text-neutral-500 uppercase tracking-wider hover:text-neutral-300 transition-colors"
      >
        <span>{open ? "▾" : "▸"}</span>
        Dataset Health
      </button>

      {open && (
        <div className="rounded-xl border border-neutral-700 bg-neutral-800/60 p-4 space-y-4">
          {loading && <p className="text-xs text-neutral-500 animate-pulse">Loading dataset health...</p>}

          {data && (
            <>
              {/* Coverage by raga */}
              {data.seed_qa?.raga_coverage && (
                <div>
                  <p className="text-xs font-medium text-neutral-400 mb-2">Source Coverage by Raga</p>
                  <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                    {Object.entries(data.seed_qa.raga_coverage)
                      .sort(([, a], [, b]) => (b as number) - (a as number))
                      .map(([raga, count]) => (
                        <div key={raga} className="rounded-lg bg-neutral-900/60 px-3 py-2">
                          <p className="text-xs font-medium text-white">{cap(raga)}</p>
                          <p className="text-sm font-bold text-amber-400">{count as number}</p>
                          <p className="text-[10px] text-neutral-500">sources</p>
                        </div>
                      ))}
                  </div>
                </div>
              )}

              {/* Rights breakdown */}
              {data.seed_qa?.rights_breakdown && (
                <div>
                  <p className="text-xs font-medium text-neutral-400 mb-2">Rights Status</p>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(data.seed_qa.rights_breakdown).map(([status, count]) => {
                      const isOk = status === "ingestible" || status === "cc";
                      return (
                        <div key={status} className={`rounded-full border px-3 py-1 text-xs ${
                          isOk
                            ? "border-green-600/30 bg-green-900/10 text-green-300"
                            : "border-amber-600/30 bg-amber-900/10 text-amber-300"
                        }`}>
                          {status}: {count as number}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Missing fields warning */}
              {data.seed_qa?.missing_fields && Object.values(data.seed_qa.missing_fields).some((v) => (v as number) > 0) && (
                <div className="rounded-lg border border-amber-800/30 bg-amber-900/10 p-3">
                  <p className="text-[11px] font-medium text-amber-400 uppercase tracking-wider mb-1">Missing Metadata</p>
                  <div className="flex flex-wrap gap-3">
                    {Object.entries(data.seed_qa.missing_fields)
                      .filter(([, count]) => (count as number) > 0)
                      .map(([field, count]) => (
                        <span key={field} className="text-xs text-amber-200/70">
                          {field}: <span className="font-mono">{count as number}</span>
                        </span>
                      ))}
                  </div>
                </div>
              )}

              {/* Phrase libraries */}
              {data.libraries && data.libraries.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-neutral-400 mb-2">Phrase Libraries</p>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-left text-neutral-500 border-b border-neutral-700">
                          <th className="pb-1.5 pr-4">Raga</th>
                          <th className="pb-1.5 pr-4">Tier</th>
                          <th className="pb-1.5 pr-4 text-right">Phrases</th>
                        </tr>
                      </thead>
                      <tbody>
                        {groupLibraries(data.libraries).map((row) => (
                          <tr key={row.raga} className="border-b border-neutral-800">
                            <td className="py-1.5 pr-4 text-white font-medium">{cap(row.raga)}</td>
                            <td className="py-1.5 pr-4">
                              <div className="flex gap-1">
                                {row.tiers.map((t) => (
                                  <span key={t.tier} className={`rounded-full bg-neutral-900/60 px-2 py-0.5 ${tierColors[t.tier] ?? "text-neutral-400"}`}>
                                    {t.tier} ({t.count})
                                  </span>
                                ))}
                              </div>
                            </td>
                            <td className="py-1.5 pr-4 text-right font-mono text-neutral-300">{row.total}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Recommender eval */}
              {data.recommender_eval?.per_raga && (
                <div>
                  <p className="text-xs font-medium text-neutral-400 mb-2">Recommender Evaluation</p>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(data.recommender_eval.per_raga).map(([raga, info]) => (
                      <div
                        key={raga}
                        className={`rounded-lg border px-3 py-1.5 text-xs ${
                          (info as { passes: boolean }).passes
                            ? "border-green-600/30 bg-green-900/10 text-green-300"
                            : "border-red-600/30 bg-red-900/10 text-red-300"
                        }`}
                      >
                        {cap(raga)}: {(info as { passes: boolean }).passes ? "Pass" : "Fail"}
                      </div>
                    ))}
                  </div>
                  {data.recommender_eval.overall_pass_rate !== undefined && (
                    <p className="text-xs text-neutral-500 mt-2">
                      Overall pass rate: <span className="font-mono text-neutral-300">{Math.round(data.recommender_eval.overall_pass_rate * 100)}%</span>
                    </p>
                  )}
                </div>
              )}

              {data.seed_qa?.generated_at && (
                <p className="text-[10px] text-neutral-600">
                  Report generated: {new Date(data.seed_qa.generated_at).toLocaleDateString()}
                </p>
              )}
            </>
          )}

          {!loading && !data && (
            <p className="text-xs text-neutral-600">No dataset health reports available yet.</p>
          )}
        </div>
      )}
    </section>
  );
}

interface GroupedLibrary {
  raga: string;
  tiers: { tier: string; count: number }[];
  total: number;
}

function groupLibraries(libs: LibraryInfo[]): GroupedLibrary[] {
  const map = new Map<string, { tier: string; count: number }[]>();
  for (const lib of libs) {
    if (!map.has(lib.raga)) map.set(lib.raga, []);
    map.get(lib.raga)!.push({ tier: lib.tier, count: lib.phrase_count });
  }
  return Array.from(map.entries())
    .map(([raga, tiers]) => ({
      raga,
      tiers,
      total: tiers.reduce((s, t) => s + t.count, 0),
    }))
    .sort((a, b) => b.total - a.total);
}
