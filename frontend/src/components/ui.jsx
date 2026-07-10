export function Spinner({ className = "h-4 w-4" }) {
  return (
    <svg className={`${className} animate-spin`} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

const TONES = {
  indigo: { chip: "bg-indigo-500/15 text-indigo-300", border: "border-indigo-500/25", text: "text-indigo-400" },
  amber: { chip: "bg-amber-500/15 text-amber-300", border: "border-amber-500/25", text: "text-amber-400" },
  teal: { chip: "bg-teal-500/15 text-teal-300", border: "border-teal-500/25", text: "text-teal-400" },
  emerald: { chip: "bg-emerald-500/15 text-emerald-300", border: "border-emerald-500/25", text: "text-emerald-400" },
  rose: { chip: "bg-rose-500/15 text-rose-300", border: "border-rose-500/25", text: "text-rose-400" },
};

export function SectionHeader({ index, title, subtitle, count, tone = "indigo" }) {
  const t = TONES[tone] || TONES.indigo;
  return (
    <div className="mb-4 flex items-end justify-between">
      <div>
        <div className="flex items-baseline gap-3">
          <span className={`font-mono text-sm font-bold ${t.text}`}>
            {String(index).padStart(2, "0")}
            <span className="text-slate-600">//</span>
          </span>
          <h2 className="font-display text-xl font-bold tracking-tight text-white">
            {title}
          </h2>
          {count != null && (
            <span className={`rounded-md px-2 py-0.5 font-mono text-xs font-bold ${t.chip}`}>
              {count}
            </span>
          )}
        </div>
        <p className="mt-1 text-sm text-slate-400">{subtitle}</p>
      </div>
    </div>
  );
}

export function StatTile({ label, value, tone = "indigo" }) {
  const t = TONES[tone] || TONES.indigo;
  return (
    <div className={`tcard rounded-xl border ${t.border} bg-slate-900/60 px-5 py-4 backdrop-blur`}>
      <p className="font-display text-3xl font-bold tabular-nums text-white">{value}</p>
      <p className={`mt-0.5 font-mono text-[10px] font-medium uppercase tracking-[0.18em] ${t.text}`}>
        {label}
      </p>
    </div>
  );
}

export function Banner({ tone = "amber", title, children }) {
  const t = TONES[tone] || TONES.amber;
  return (
    <div className={`rounded-xl border ${t.border} bg-slate-900/60 px-5 py-4 text-sm`}>
      {title && (
        <p className={`mb-1 font-mono text-xs font-bold uppercase tracking-widest ${t.text}`}>
          ⚠ {title}
        </p>
      )}
      <p className="leading-relaxed text-slate-300">{children}</p>
    </div>
  );
}

export function EmptyState({ children }) {
  return (
    <p className="rounded-xl border border-dashed border-slate-800 bg-slate-900/30 px-5 py-6 text-center text-sm text-slate-500">
      <span className="mr-2 font-mono text-slate-600">[no signal]</span>
      {children}
    </p>
  );
}
