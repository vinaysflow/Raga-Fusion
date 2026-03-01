export default function Spinner({ label = "Generating..." }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-6">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-neutral-600 border-t-amber-400" />
      <span className="text-neutral-400 text-sm">{label}</span>
    </div>
  );
}
