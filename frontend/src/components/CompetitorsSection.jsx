import { useState } from "react";
import { SectionHeader, EmptyState } from "./ui.jsx";

function Favicon({ website, name }) {
  const domain = website
    ? website.replace(/^https?:\/\//, "").split("/")[0]
    : "";
  const [err, setErr] = useState(false);
  if (!domain || err) {
    return (
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 text-sm font-bold text-white">
        {name.slice(0, 1)}
      </div>
    );
  }
  return (
    <img
      src={`https://www.google.com/s2/favicons?domain=${domain}&sz=64`}
      alt=""
      onError={() => setErr(true)}
      className="h-9 w-9 shrink-0 rounded-lg border border-slate-700/60 bg-slate-800 p-1.5"
      loading="lazy"
    />
  );
}

function CompetitorCard({ c }) {
  return (
    <div className="tcard group rounded-xl border border-slate-800 bg-slate-900/60 p-5 transition hover:border-indigo-500/40 hover:bg-slate-900 hover:shadow-lg hover:shadow-indigo-500/5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <Favicon website={c.website} name={c.name} />
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
          <span className="rounded-md bg-slate-800 px-2 py-1 font-mono text-[11px] font-medium text-slate-400">
            lock {Math.min(c.confidence, 99)}%
          </span>
        )}
      </div>
      <p className="mt-3 text-sm leading-relaxed text-slate-400">{c.description}</p>
    </div>
  );
}

export default function CompetitorsSection({ competitors }) {
  return (
    <section id="competitors" className="scroll-mt-32">
      <SectionHeader
        index="1"
        title="Direct Competitors"
        subtitle="Verified companies competing for the same buyers"
        count={competitors.length}
        tone="indigo"
      />
      {competitors.length ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {competitors.map((c) => (
            <CompetitorCard key={c.name} c={c} />
          ))}
        </div>
      ) : (
        <EmptyState>No competitors could be verified from live sources.</EmptyState>
      )}
    </section>
  );
}
