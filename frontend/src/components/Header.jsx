export default function Header({ data, onRerun }) {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <div className="flex items-center gap-3">
          {/* crosshair lens mark */}
          <div className="relative flex h-9 w-9 items-center justify-center rounded-full border border-indigo-400/60 bg-slate-900">
            <div className="h-2 w-2 rounded-full bg-gradient-to-br from-indigo-400 to-amber-300" />
            <span className="absolute -left-0.5 top-1/2 h-px w-2 -translate-y-1/2 bg-indigo-400/70" />
            <span className="absolute -right-0.5 top-1/2 h-px w-2 -translate-y-1/2 bg-indigo-400/70" />
            <span className="absolute -top-0.5 left-1/2 h-2 w-px -translate-x-1/2 bg-indigo-400/70" />
            <span className="absolute -bottom-0.5 left-1/2 h-2 w-px -translate-x-1/2 bg-indigo-400/70" />
          </div>
          <div>
            <h1 className="font-display text-lg font-bold tracking-tight text-white">
              LeadLens
            </h1>
            <p className="-mt-1 font-mono text-[10px] uppercase tracking-[0.25em] text-slate-500">
              market recon
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <span className="hidden items-center gap-2 font-mono text-[10px] uppercase tracking-widest text-emerald-400/90 sm:flex">
            <span className="status-dot h-1.5 w-1.5 rounded-full bg-emerald-400" />
            live &amp; scanning
          </span>
          {data && (
            <button
              onClick={onRerun}
              className="rounded-lg border border-slate-700 px-3 py-1.5 font-mono text-xs font-semibold text-slate-300 transition hover:border-indigo-400/60 hover:text-white"
            >
              ↻ re-scan
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
