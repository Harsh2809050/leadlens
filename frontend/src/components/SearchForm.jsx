import { Spinner } from "./ui.jsx";

export default function SearchForm({
  company, setCompany, location, setLocation,
  loading, history, data, onSubmit, onHistoryPick,
}) {
  return (
    <section className="py-14 text-center">
      <p className="mb-3 font-mono text-[11px] uppercase tracking-[0.3em] text-indigo-400/80">
        [ target acquisition ]
      </p>
      <h2 className="font-display text-4xl font-bold tracking-tight text-white sm:text-5xl">
        Point it at a company.
        <br />
        <span className="bg-gradient-to-r from-indigo-400 via-violet-400 to-amber-300 bg-clip-text text-transparent">
          Get the whole battlefield.
        </span>
      </h2>
      <p className="mx-auto mt-4 max-w-xl text-sm leading-relaxed text-slate-400">
        Who they fight, who buys from them, where their customers hang out,
        and what could kill them — pulled from the live web while you watch,
        then cached forever.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
        className="mx-auto mt-9 flex max-w-3xl flex-col gap-3 sm:flex-row"
      >
        <input
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          placeholder="company — e.g. Notion"
          className="flex-[1.4] rounded-xl border border-slate-700 bg-slate-900/80 px-4 py-3 font-mono text-sm text-white placeholder-slate-500 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30"
        />
        <input
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          placeholder="city — optional"
          className="flex-1 rounded-xl border border-slate-700 bg-slate-900/80 px-4 py-3 font-mono text-sm text-white placeholder-slate-500 outline-none transition focus:border-amber-500 focus:ring-2 focus:ring-amber-500/30"
        />
        <button
          type="submit"
          disabled={loading || !company.trim()}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-7 py-3 font-display text-sm font-bold text-white shadow-lg shadow-indigo-600/25 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {loading ? <Spinner /> : "Run scan ▸"}
        </button>
      </form>
      <p className="mx-auto mt-3 max-w-md text-xs text-slate-500">
        A city sharpens B2C recon — the cafés, coaching institutes and
        gamezones where your audience actually hangs out. Blank = global sweep.
      </p>

      {history.length > 0 && !data && !loading && (
        <div className="mt-7 flex flex-wrap items-center justify-center gap-2">
          <span className="font-mono text-[10px] uppercase tracking-widest text-slate-500">
            previous scans:
          </span>
          {history.slice(0, 6).map((h) => (
            <button
              key={h.company + h.industry + (h.location || "")}
              onClick={() => onHistoryPick(h)}
              className="rounded-full border border-slate-800 bg-slate-900 px-3 py-1 text-xs text-slate-300 transition hover:border-indigo-500/50 hover:text-white"
            >
              {h.company}
              <span className="ml-1 text-slate-500">
                · {h.industry}{h.location ? ` · ${h.location}` : ""}
              </span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
