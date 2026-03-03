import { Link, Outlet } from "react-router-dom";

export default function ProviderLayout() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-[#0A0A0F] to-[#121425] text-white">
      <header className="border-b border-white/10">
        <div className="max-w-4xl mx-auto px-4 py-5 flex items-center justify-between">
          <div className="space-y-1">
            <h1 className="text-lg font-semibold tracking-tight">
              Provider Portal
            </h1>
            <p className="text-xs text-neutral-400">
              Upload raga performances and approve phrase libraries
            </p>
          </div>
          <Link
            to="/create"
            className="text-xs text-neutral-300 hover:text-white border border-white/10 rounded-full px-3 py-1"
          >
            Back to Generator
          </Link>
        </div>
      </header>
      <main className="max-w-4xl mx-auto px-4 py-8">
        <Outlet />
      </main>
    </div>
  );
}
