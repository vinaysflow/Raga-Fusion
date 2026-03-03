import { Link } from "react-router-dom";

export default function RoleSelect() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-[#0A0A0F] to-[#1A1A2E] text-white flex flex-col items-center justify-center px-4">
      <div className="max-w-lg w-full space-y-10">
        <header className="text-center space-y-2">
          <h1 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-amber-400 to-orange-400 bg-clip-text text-transparent">
            Raga-Fusion Music Generator
          </h1>
          <p className="text-neutral-500 text-sm">
            Indian classical raga meets modern production
          </p>
        </header>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Link
            to="/create"
            className="group relative overflow-hidden rounded-2xl border border-white/10 bg-white/5 p-6 text-left transition-all hover:border-amber-500/50 hover:bg-amber-500/10 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
          >
            <span className="text-3xl" aria-hidden>✨</span>
            <h2 className="mt-3 text-lg font-semibold text-white">Creator</h2>
            <p className="mt-1 text-sm text-neutral-400">
              Generate fusion tracks. Describe your vibe, pick raga and style, get a track.
            </p>
            <span className="mt-4 inline-block text-sm font-medium text-amber-400 group-hover:text-amber-300">
              Start creating →
            </span>
          </Link>

          <Link
            to="/provider"
            className="group relative overflow-hidden rounded-2xl border border-white/10 bg-white/5 p-6 text-left transition-all hover:border-indigo-500/50 hover:bg-indigo-500/10 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
          >
            <span className="text-3xl" aria-hidden>🎵</span>
            <h2 className="mt-3 text-lg font-semibold text-white">Provider</h2>
            <p className="mt-1 text-sm text-neutral-400">
              Upload raga performances. Contribute phrase libraries for creators to use.
            </p>
            <span className="mt-4 inline-block text-sm font-medium text-indigo-400 group-hover:text-indigo-300">
              Go to provider portal →
            </span>
          </Link>
        </div>
      </div>
    </div>
  );
}
