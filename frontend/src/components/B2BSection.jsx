import { useState } from "react";
import { SectionHeader, EmptyState } from "./ui.jsx";
import { downloadCsv, ExportButton } from "./exportCsv.jsx";

function LeadsTable({ leads }) {
  const [page, setPage] = useState(0);
  const [personaFilter, setPersonaFilter] = useState(null);
  const PER_PAGE = 10;

  const personas = [...new Set(leads.map((l) => l.persona).filter(Boolean))];
  const filtered = personaFilter
    ? leads.filter((l) => l.persona === personaFilter)
    : leads;
  const pages = Math.max(1, Math.ceil(filtered.length / PER_PAGE));
  const safePage = Math.min(page, pages - 1);
  const visible = filtered.slice(safePage * PER_PAGE, (safePage + 1) * PER_PAGE);

  return (
    <div>
      {personas.length > 1 && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <button
            onClick={() => { setPersonaFilter(null); setPage(0); }}
            className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
              !personaFilter
                ? "bg-teal-600 text-white"
                : "border border-slate-700 text-slate-400 hover:text-white"
            }`}
          >
            All ({leads.length})
          </button>
          {personas.map((p) => (
            <button
              key={p}
              onClick={() => { setPersonaFilter(p); setPage(0); }}
              className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                personaFilter === p
                  ? "bg-teal-600 text-white"
                  : "border border-slate-700 text-slate-400 hover:text-white"
              }`}
            >
              {p} ({leads.filter((l) => l.persona === p).length})
            </button>
          ))}
        </div>
      )}

      <div className="overflow-x-auto rounded-xl border border-slate-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-900 text-xs uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-5 py-3 font-semibold">Name</th>
              <th className="px-5 py-3 font-semibold">Role</th>
              <th className="px-5 py-3 font-semibold">Persona match</th>
              <th className="px-5 py-3 font-semibold">LinkedIn</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/80 bg-slate-900/40">
            {visible.map((l) => (
              <tr key={l.linkedin_url} className="transition hover:bg-slate-800/40">
                <td className="px-5 py-3.5 font-medium text-white">{l.name}</td>
                <td className="max-w-xs truncate px-5 py-3.5 text-slate-300">
                  {l.role || "—"}
                </td>
                <td className="px-5 py-3.5">
                  <span className="rounded-md bg-teal-500/10 px-2 py-0.5 text-xs font-medium text-teal-300">
                    {l.persona || l.company || "—"}
                  </span>
                </td>
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

      {pages > 1 && (
        <div className="mt-3 flex items-center justify-center gap-1.5">
          <button
            onClick={() => setPage(Math.max(0, safePage - 1))}
            disabled={safePage === 0}
            className="rounded-lg border border-slate-700 px-2.5 py-1 text-xs text-slate-300 disabled:opacity-30"
          >
            ←
          </button>
          {Array.from({ length: pages }, (_, i) => (
            <button
              key={i}
              onClick={() => setPage(i)}
              className={`h-7 w-7 rounded-lg text-xs font-semibold transition ${
                i === safePage
                  ? "bg-teal-600 text-white"
                  : "border border-slate-700 text-slate-400 hover:text-white"
              }`}
            >
              {i + 1}
            </button>
          ))}
          <button
            onClick={() => setPage(Math.min(pages - 1, safePage + 1))}
            disabled={safePage === pages - 1}
            className="rounded-lg border border-slate-700 px-2.5 py-1 text-xs text-slate-300 disabled:opacity-30"
          >
            →
          </button>
        </div>
      )}
    </div>
  );
}

export default function B2BSection({ leads }) {
  function exportLeads() {
    downloadCsv("leadlens_b2b_leads.csv", leads, [
      { label: "Name", get: (l) => l.name },
      { label: "Role", get: (l) => l.role },
      { label: "Persona", get: (l) => l.persona },
      { label: "LinkedIn URL", get: (l) => l.linkedin_url },
    ]);
  }
  return (
    <section id="b2b" className="scroll-mt-32">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <SectionHeader
          index="2"
          title="B2B Decision-Makers"
          subtitle="Prospective buyers worldwide whose job titles match this product's customer profile"
          count={leads.length}
          tone="teal"
        />
        {leads.length > 0 && (
          <ExportButton onClick={exportLeads} count={leads.length} tone="teal" />
        )}
      </div>
      {leads.length ? (
        <LeadsTable leads={leads} />
      ) : (
        <EmptyState>No LinkedIn decision makers surfaced for this search.</EmptyState>
      )}
    </section>
  );
}
