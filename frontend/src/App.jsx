import { useEffect, useState } from "react";
import Header from "./components/Header.jsx";
import SearchForm from "./components/SearchForm.jsx";
import StatStrip from "./components/StatStrip.jsx";
import TabNav from "./components/TabNav.jsx";
import CompetitorsSection from "./components/CompetitorsSection.jsx";
import B2BSection from "./components/B2BSection.jsx";
import B2CSection from "./components/B2CSection.jsx";
import ReportSection from "./components/ReportSection.jsx";
import SourcesSection from "./components/SourcesSection.jsx";
import { Spinner, Banner } from "./components/ui.jsx";

const LOADING_STEPS = [
  "Working out what this company actually does…",
  "Reading their homepage so you don't have to…",
  "Hunting down everyone they compete with…",
  "Making competitors prove they're real…",
  "Finding the people who'd actually buy this…",
  "Scouting the cafés and campuses their customers haunt…",
  "Collecting receipts (market stats, trends)…",
  "Interrogating six search engines at once…",
  "Writing the report a consultant would bill for…",
];

export default function App() {
  const [company, setCompany] = useState("");
  const [location, setLocation] = useState("");
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

  async function runSearch(c = company, loc = location, ind = "", refresh = false) {
    if (!c.trim()) return;
    setLoading(true);
    setStep(0);
    setError("");
    setData(null);
    try {
      const params = new URLSearchParams({
        company: c.trim(),
        industry: (ind || "").trim(),
        location: (loc || "").trim(),
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

  const leads = data?.leads || [];
  const b2bLeads = leads.filter((l) => l.segment === "b2b");
  const venues = leads.filter((l) => l.lead_type === "venue");
  const individuals = leads.filter((l) => l.lead_type === "individual");

  return (
    <div className="min-h-screen bg-slate-950 font-sans text-slate-200">
      {/* blueprint dot-grid + focused glow backdrop */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="dotgrid absolute inset-x-0 top-0 h-[520px]" />
        <div className="absolute -top-32 left-1/2 h-96 w-[42rem] -translate-x-1/2 rounded-full bg-indigo-600/10 blur-3xl" />
        <div className="absolute top-40 right-1/4 h-64 w-64 rounded-full bg-amber-500/5 blur-3xl" />
      </div>

      <Header data={data} onRerun={() => runSearch(data.company, data.location, data.industry, true)} />

      <main className="relative mx-auto max-w-6xl px-6 pb-24">
        <SearchForm
          company={company}
          setCompany={setCompany}
          location={location}
          setLocation={setLocation}
          loading={loading}
          history={history}
          data={data}
          onSubmit={() => runSearch()}
          onHistoryPick={(h) => {
            setCompany(h.company);
            setIndustry(h.industry);
            setLocation(h.location || "");
            runSearch(h.company, h.location || "", h.industry);
          }}
        />

        {/* loading — radar sweep */}
        {loading && (
          <div className="tcard mx-auto max-w-md rounded-2xl border border-slate-800 bg-slate-900/60 p-8 text-center">
            <div className="radar mx-auto mb-5 h-20 w-20">
              <span className="radar-blip" style={{ top: "30%", left: "62%" }} />
              <span className="radar-blip" style={{ top: "58%", left: "28%", animationDelay: "0.9s" }} />
              <span className="radar-blip" style={{ top: "70%", left: "60%", animationDelay: "1.6s" }} />
            </div>
            <p className="font-mono text-[10px] uppercase tracking-[0.3em] text-indigo-400/80">
              scan in progress
            </p>
            <p className="caret mt-2 text-sm font-semibold text-white">
              {LOADING_STEPS[step]}
            </p>
            <p className="mt-3 text-xs text-slate-500">
              First scan of a company takes 2–4 minutes — it's doing real
              recon, not fetching a database row. Repeats are instant.
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
          <>
            <TabNav />
            <div className="space-y-14">
              {/* meta bar */}
              <div className="tcard flex flex-wrap items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/60 px-5 py-3.5 text-sm">
                <span className="font-mono text-xs text-indigo-400">⌖</span>
                <span className="font-display font-bold text-white">{data.company}</span>
                <span className="rounded-md bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-300">
                  {data.industry}
                </span>
                {data.location && (
                  <span className="rounded-md bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-300">
                    📍 {data.location}
                  </span>
                )}
                <span
                  className={`ml-auto rounded-full px-2.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-widest ${
                    data.cached
                      ? "bg-amber-500/15 text-amber-400"
                      : "bg-emerald-500/15 text-emerald-400"
                  }`}
                >
                  {data.cached ? "⚡ cache hit" : "● fresh recon"}
                </span>
                <span className="font-mono text-xs text-slate-500">
                  {new Date(data.researched_at * 1000).toLocaleString()}
                </span>
              </div>

              {data.low_confidence && (
                <Banner tone="amber" title="Low-confidence result">
                  We couldn't verify a public web presence for "{data.company}"
                  — it may be new, very small, or misspelled. Competitor and
                  report data below may be sparse; nothing has been fabricated
                  to fill the gaps.
                </Banner>
              )}

              {data.degraded && (
                <Banner tone="rose" title="Rate-limited during this run">
                  Search engines were rate-limiting this server while
                  researching "{data.company}" — some sections below may be
                  incomplete for that reason, not because the data doesn't
                  exist. Try "Re-run research" in a few minutes.
                </Banner>
              )}

              <StatStrip
                competitors={data.competitors.length}
                b2bLeads={b2bLeads.length}
                venues={venues.length}
                individuals={individuals.length}
              />

              <CompetitorsSection competitors={data.competitors} />
              <B2BSection leads={b2bLeads} />
              <B2CSection venues={venues} individuals={individuals} />
              <ReportSection report={data.report} />
              <SourcesSection sources={data.sources} />
            </div>
          </>
        )}
      </main>

      <footer className="relative border-t border-slate-800/80 py-6 text-center font-mono text-[11px] text-slate-600">
        LeadLens · every claim links back to a source · no fabricated data, ever
      </footer>
    </div>
  );
}
