import { useEffect, useState } from "react";

const LOADING_STEPS = [
  "Identifying the company's industry…",
  "Scanning the web for direct competitors…",
  "Verifying competitor companies…",
  "Finding decision makers on LinkedIn…",
  "Reading company positioning…",
  "Pulling industry trends and market data…",
  "Writing the intelligence report…",
];

function Spinner() {
  return (
    <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

function SectionHeader({ index, title, subtitle, count }) {
  return (
    <div className="mb-4 flex items-end justify-between">
      <div>
        <div className="flex items-center gap-3">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/15 text-sm font-bold text-indigo-400">
            {index}
          </span>
          <h2 className="text-lg font-bold text-white">{title}</h2>
          {count != null && (
            <span className="rounded-full bg-slate-800 px-2.5 py-0.5 text-xs font-semibold text-slate-300">
              {count}
            </span>
          )}
        </div>
        <p className="ml-10 mt-0.5 text-sm text-slate-400">{subtitle}</p>
      </div>
    </div>
  );
}

function CompetitorCard({ c }) {
  return (
    <div className="group rounded-xl border border-slate-800 bg-slate-900/60 p-5 transition hover:border-indigo-500/40 hover:bg-slate-900">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 text-sm font-bold text-white">
            {c.name.slice(0, 1)}
          </div>
          <div>
            <h3 className="font-semibold text-white">{c.name}</h3>
            {c.website && (
              <a
                href={c.website}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-indigo-400 hover:underline"
              >
                {c.website.replace(/^https?:\/\//, "")}
              </a>
            )}
          </div>
        </div>
        {c.confidence != null && (
          <span className="rounded-md bg-slate-800 px-2 py-1 text-[11px] font-medium text-slate-400">
            match {Math.min(c.confidence, 99)}%
          </span>
        )}
      </div>
      <p className="mt-3 text-sm leading-relaxed text-slate-400">{c.description}</p>
    </div>
  );
}

function LeadsTable({ leads }) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-800">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-900 text-xs uppercase tracking-wider text-slate-500">
          <tr>
            <th className="px-5 py-3 font-semibold">Name</th>
            <th className="px-5 py-3 font-semibold">Role</th>
            <th className="px-5 py-3 font-semibold">Company</th>
            <th className="px-5 py-3 font-semibold">LinkedIn</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/80 bg-slate-900/40">
          {leads.map((l) => (
            <tr key={l.linkedin_url} className="transition hover:bg-slate-800/40">
              <td className="px-5 py-3.5 font-medium text-white">
                {l.name}
                {l.is_target_company && (
                  <span className="ml-2 rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-bold text-emerald-400">
                    TARGET
                  </span>
                )}
              </td>
              <td className="px-5 py-3.5 text-slate-300">{l.role || "—"}</td>
              <td className="px-5 py-3.5 text-slate-300">{l.company}</td>
              <td className="px-5 py-3.5">
                <a
                  href={l.linkedin_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-md bg-[#0a66c2]/15 px-2.5 py-1 text-xs font-semibold text-[#4da3ff] transition hover:bg-[#0a66c2]/30"
                >
                  <svg className="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M19 0h-14c-2.76 0-5 2.24-5 5v14c0 2.76 2.24 5 5 5h14c2.76 0 5-2.24 5-5v-14c0-2.76-2.24-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.27c-.97 0-1.75-.79-1.75-1.76s.78-1.75 1.75-1.75 1.75.78 1.75 1.75-.78 1.76-1.75 1.76zm13.5 12.27h-3v-5.6c0-3.37-4-3.11-4 0v5.6h-3v-11h3v1.77c1.4-2.59 7-2.78 7 2.47v6.76z" />
                  </svg>
                  Profile
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReportBlock({ icon, tone, title, items }) {
  const toneClasses =
    tone === "growth"
      ? { border: "border-emerald-500/25", chip: "bg-emerald-500/15 text-emerald-400" }
      : { border: "border-rose-500/25", chip: "bg-rose-500/15 text-rose-400" };
  return (
    <div className={`rounded-xl border ${toneClasses.border} bg-slate-900/60 p-6`}>
      <div className="mb-4 flex items-center gap-2.5">
        <span className={`flex h-8 w-8 items-center justify-center rounded-lg text-base ${toneClasses.chip}`}>
          {icon}
        </span>
        <h3 className="font-bold text-white">{title}</h3>
      </div>
      <ol className="space-y-5">
        {items.map((item, i) => (
          <li key={i}>
            <p className="mb-1 text-sm font-semibold text-slate-100">
              {i + 1}. {item.title}
            </p>
            <p className="text-sm leading-relaxed text-slate-400">{item.detail}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}

export default function App() {
  const [company, setCompany] = useState("");
  const [industry, setIndustry] = useState("");
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState(0);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [history, setHistory] = useState([]);

  useEffect(() => {
    fetch("/api/history")
      .then((r) => r.json())
      .then((d) => setHistory(d.searches || []))
      .catch(() => {});
  }, [data]);

  useEffect(() => {
    if (!loading) return;
    const t = setInterval(
      () => setStep((s) => (s + 1) % LOADING_STEPS.length),
      4000
    );
    return () => clearInterval(t);
  }, [loading]);

  async function runSearch(c = company, ind = "", refresh = false) {
    if (!c.trim()) return;
    setLoading(true);
    setStep(0);
    setError("");
    setData(null);
    try {
      const params = new URLSearchParams({
        company: c.trim(),
        industry: (ind || "").trim(),
        refresh: refresh ? "1" : "0",
      });
      const res = await fetch(`/api/search?${params}`);
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || "Research failed");
      setData(body);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 font-sans text-slate-200">
      {/* backdrop glow */}
      <div className="pointer-events-none fixed inset-x-0 top-0 h-96 bg-gradient-to-b from-indigo-600/10 to-transparent" />

      <header className="relative border-b border-slate-800/80">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 font-black text-white">
              L
            </div>
            <div>
              <h1 className="text-lg font-extrabold tracking-tight text-white">
                LeadLens
              </h1>
              <p className="-mt-0.5 text-[11px] font-medium uppercase tracking-widest text-slate-500">
                Lead Intelligence
              </p>
            </div>
          </div>
          {data && (
            <button
              onClick={() => runSearch(data.company, data.industry, true)}
              className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300 transition hover:border-slate-500 hover:text-white"
            >
              ↻ Re-run research
            </button>
          )}
        </div>
      </header>

      <main className="relative mx-auto max-w-5xl px-6 pb-24">
        {/* search */}
        <section className="py-12 text-center">
          <h2 className="text-3xl font-extrabold tracking-tight text-white sm:text-4xl">
            Know any company&apos;s battlefield{" "}
            <span className="bg-gradient-to-r from-indigo-400 to-violet-400 bg-clip-text text-transparent">
              in one search
            </span>
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-sm text-slate-400">
            Competitors, decision-maker leads and a live business intelligence
            report — researched from the real web, cached forever.
          </p>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              runSearch();
            }}
            className="mx-auto mt-8 flex max-w-2xl flex-col gap-3 sm:flex-row"
          >
            <input
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              placeholder="Type a company name — e.g. Notion"
              className="flex-1 rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-white placeholder-slate-500 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30"
            />
            <button
              type="submit"
              disabled={loading || !company.trim()}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-6 py-3 text-sm font-bold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {loading ? <Spinner /> : "Analyze"}
            </button>
          </form>

          {history.length > 0 && !data && !loading && (
            <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
              <span className="text-xs text-slate-500">Recent:</span>
              {history.slice(0, 6).map((h) => (
                <button
                  key={h.company + h.industry}
                  onClick={() => {
                    setCompany(h.company);
                    setIndustry(h.industry);
                    runSearch(h.company, h.industry);
                  }}
                  className="rounded-full border border-slate-800 bg-slate-900 px-3 py-1 text-xs text-slate-300 transition hover:border-indigo-500/50 hover:text-white"
                >
                  {h.company}
                  <span className="ml-1 text-slate-500">· {h.industry}</span>
                </button>
              ))}
            </div>
          )}
        </section>

        {/* loading */}
        {loading && (
          <div className="mx-auto max-w-md rounded-2xl border border-slate-800 bg-slate-900/60 p-8 text-center">
            <div className="mx-auto mb-4 flex h-10 w-10 items-center justify-center rounded-full bg-indigo-500/15 text-indigo-400">
              <Spinner />
            </div>
            <p className="text-sm font-semibold text-white">
              {LOADING_STEPS[step]}
            </p>
            <p className="mt-2 text-xs text-slate-500">
              Live web research takes 1–3 minutes the first time. Repeat
              searches are instant (cached).
            </p>
          </div>
        )}

        {/* error */}
        {error && (
          <div className="mx-auto max-w-xl rounded-xl border border-rose-500/30 bg-rose-500/10 px-5 py-4 text-sm text-rose-300">
            <span className="font-bold">Research failed: </span>
            {error}
          </div>
        )}

        {/* results */}
        {data && (
          <div className="space-y-14">
            {/* meta bar */}
            <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/60 px-5 py-3.5 text-sm">
              <span className="font-bold text-white">{data.company}</span>
              <span className="text-slate-500">·</span>
              <span className="text-slate-300">{data.industry}</span>
              <span
                className={`ml-auto rounded-full px-2.5 py-0.5 text-[11px] font-bold ${
                  data.cached
                    ? "bg-amber-500/15 text-amber-400"
                    : "bg-emerald-500/15 text-emerald-400"
                }`}
              >
                {data.cached ? "⚡ FROM CACHE" : "● LIVE RESEARCH"}
              </span>
              <span className="text-xs text-slate-500">
                {new Date(data.researched_at * 1000).toLocaleString()}
              </span>
            </div>

            {/* competitors */}
            <section>
              <SectionHeader
                index="1"
                title="Direct Competitors"
                subtitle="Verified companies competing for the same buyers"
                count={data.competitors.length}
              />
              {data.competitors.length ? (
                <div className="grid gap-4 sm:grid-cols-2">
                  {data.competitors.map((c) => (
                    <CompetitorCard key={c.name} c={c} />
                  ))}
                </div>
              ) : (
                <p className="text-sm text-slate-500">
                  No competitors could be verified from live sources.
                </p>
              )}
            </section>

            {/* leads */}
            <section>
              <SectionHeader
                index="2"
                title="Potential Leads"
                subtitle="Decision makers found via LinkedIn across the competitive set"
                count={data.leads.length}
              />
              {data.leads.length ? (
                <LeadsTable leads={data.leads} />
              ) : (
                <p className="text-sm text-slate-500">
                  No LinkedIn decision makers surfaced for this search.
                </p>
              )}
            </section>

            {/* report */}
            <section>
              <SectionHeader
                index="3"
                title="Business Intelligence Report"
                subtitle="Analyst view built from competitor, positioning and trend data"
              />
              {data.report?.summary && (
                <div className="mb-5 rounded-xl border border-indigo-500/25 bg-indigo-500/5 p-6">
                  <p className="mb-1.5 text-[11px] font-bold uppercase tracking-widest text-indigo-400">
                    Executive summary
                  </p>
                  <p className="text-sm leading-relaxed text-slate-300">
                    {data.report.summary}
                  </p>
                </div>
              )}
              <div className="grid gap-5 lg:grid-cols-2">
                <ReportBlock
                  icon="▲"
                  tone="growth"
                  title="3 things that can grow this company"
                  items={data.report?.growth || []}
                />
                <ReportBlock
                  icon="▼"
                  tone="risk"
                  title="3 things that can kill it"
                  items={data.report?.risks || []}
                />
              </div>
            </section>

            {/* sources */}
            {data.sources?.length > 0 && (
              <section className="rounded-xl border border-slate-800/80 bg-slate-900/40 p-5">
                <p className="mb-2 text-xs font-bold uppercase tracking-widest text-slate-500">
                  Sources consulted ({data.sources.length})
                </p>
                <div className="flex flex-wrap gap-x-4 gap-y-1">
                  {data.sources.map((s) => (
                    <a
                      key={s}
                      href={s}
                      target="_blank"
                      rel="noreferrer"
                      className="max-w-xs truncate text-xs text-slate-500 hover:text-indigo-400"
                    >
                      {s.replace(/^https?:\/\/(www\.)?/, "")}
                    </a>
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
      </main>

      <footer className="border-t border-slate-800/80 py-6 text-center text-xs text-slate-600">
        LeadLens · live web research, SQLite-cached · results link to original sources
      </footer>
    </div>
  );
}
