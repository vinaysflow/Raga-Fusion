import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getRagas, registerProvider, type ProviderRegisterPayload, type RagaInfo } from "../api";

const GHARANAS = [
  "Jaipur",
  "Kirana",
  "Agra",
  "Gwalior",
  "Patiala",
  "Self-taught",
  "Other",
];

const INSTRUMENTS = [
  "Vocal",
  "Sitar",
  "Sarod",
  "Bansuri",
  "Sarangi",
  "Harmonium",
  "Veena",
  "Other",
];

export default function ProviderOnboarding() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [ragas, setRagas] = useState<RagaInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState<ProviderRegisterPayload>({
    name: "",
    email: "",
    gharana: "",
    instruments: [],
    training_lineage: "",
    bio: "",
  });
  const [preferredRaga, setPreferredRaga] = useState("yaman");
  const [declaredSa, setDeclaredSa] = useState("");

  useEffect(() => {
    getRagas().then(setRagas).catch(() => {});
  }, []);

  const canContinue = useMemo(() => {
    if (step === 0) return form.name.trim().length > 1;
    if (step === 1) return true;
    if (step === 2) return preferredRaga.trim().length > 0;
    return false;
  }, [step, form.name, preferredRaga]);

  function toggleInstrument(name: string) {
    setForm((prev) => {
      const next = new Set(prev.instruments || []);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return { ...prev, instruments: Array.from(next) };
    });
  }

  async function handleSubmit() {
    setLoading(true);
    setError(null);
    try {
      const payload: ProviderRegisterPayload = {
        ...form,
        gharana: form.gharana || undefined,
        instruments: form.instruments || [],
        training_lineage: form.training_lineage || undefined,
        bio: form.bio || undefined,
        email: form.email || undefined,
      };
      const provider = await registerProvider(payload);
      localStorage.setItem("provider_id", provider.id);
      localStorage.setItem("provider_default_raga", preferredRaga);
      if (declaredSa) localStorage.setItem("provider_declared_sa", declaredSa);
      navigate("/provider/upload");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h2 className="text-2xl font-semibold">Musician Onboarding</h2>
        <p className="text-sm text-neutral-400">
          Create your provider profile to upload and review raga phrase libraries.
        </p>
      </div>

      <div className="flex items-center gap-2 text-xs text-neutral-500">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className={`h-1.5 w-8 rounded-full ${i <= step ? "bg-indigo-400" : "bg-white/10"}`}
          />
        ))}
      </div>

      {step === 0 && (
        <div className="space-y-4">
          <div>
            <label className="text-sm text-neutral-300">Full name</label>
            <input
              className="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm"
              value={form.name}
              onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
              placeholder="Pandit Anirudh Kumar"
            />
          </div>
          <div>
            <label className="text-sm text-neutral-300">Email (optional)</label>
            <input
              className="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm"
              value={form.email ?? ""}
              onChange={(e) => setForm((prev) => ({ ...prev, email: e.target.value }))}
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label className="text-sm text-neutral-300">Gharana</label>
            <select
              className="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm"
              value={form.gharana ?? ""}
              onChange={(e) => setForm((prev) => ({ ...prev, gharana: e.target.value }))}
            >
              <option value="">Select gharana</option>
              {GHARANAS.map((g) => (
                <option key={g} value={g.toLowerCase()}>
                  {g}
                </option>
              ))}
            </select>
          </div>
          <div>
            <p className="text-sm text-neutral-300 mb-2">Instruments</p>
            <div className="flex flex-wrap gap-2">
              {INSTRUMENTS.map((inst) => {
                const active = form.instruments?.includes(inst);
                return (
                  <button
                    key={inst}
                    type="button"
                    onClick={() => toggleInstrument(inst)}
                    className={`rounded-full px-3 py-1 text-xs border ${
                      active
                        ? "border-indigo-400 bg-indigo-500/20 text-indigo-200"
                        : "border-white/10 text-neutral-300"
                    }`}
                  >
                    {inst}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {step === 1 && (
        <div className="space-y-4">
          <div>
            <label className="text-sm text-neutral-300">Training lineage</label>
            <textarea
              className="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm min-h-[90px]"
              value={form.training_lineage ?? ""}
              onChange={(e) => setForm((prev) => ({ ...prev, training_lineage: e.target.value }))}
              placeholder="Studied under..."
            />
          </div>
          <div>
            <label className="text-sm text-neutral-300">Short bio</label>
            <textarea
              className="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm min-h-[90px]"
              value={form.bio ?? ""}
              onChange={(e) => setForm((prev) => ({ ...prev, bio: e.target.value }))}
              placeholder="A few lines about your performance background..."
            />
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-4">
          <div>
            <label className="text-sm text-neutral-300">Primary raga for this upload</label>
            <select
              className="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm"
              value={preferredRaga}
              onChange={(e) => setPreferredRaga(e.target.value)}
            >
              {ragas.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-sm text-neutral-300">Declared Sa (tonic)</label>
            <input
              className="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm"
              value={declaredSa}
              onChange={(e) => setDeclaredSa(e.target.value.toUpperCase())}
              placeholder="C, C#, D, Eb..."
            />
            <p className="text-xs text-neutral-500 mt-1">
              If you are unsure, you can leave this blank and we will auto-detect.
            </p>
          </div>
        </div>
      )}

      {error && (
        <div className="rounded-lg bg-red-900/30 border border-red-800 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <div className="flex items-center justify-between">
        <button
          type="button"
          className="text-xs text-neutral-400"
          onClick={() => setStep((s) => Math.max(0, s - 1))}
          disabled={step === 0}
        >
          Back
        </button>
        {step < 2 ? (
          <button
            type="button"
            className="rounded-full bg-indigo-500 px-4 py-2 text-xs font-semibold text-white disabled:opacity-50"
            disabled={!canContinue}
            onClick={() => setStep((s) => s + 1)}
          >
            Next
          </button>
        ) : (
          <button
            type="button"
            className="rounded-full bg-indigo-500 px-4 py-2 text-xs font-semibold text-white disabled:opacity-50"
            disabled={!canContinue || loading}
            onClick={handleSubmit}
          >
            {loading ? "Registering..." : "Create Profile"}
          </button>
        )}
      </div>
    </div>
  );
}
