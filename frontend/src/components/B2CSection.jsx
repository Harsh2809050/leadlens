import { SectionHeader, EmptyState } from "./ui.jsx";
import { downloadCsv, ExportButton } from "./exportCsv.jsx";

function ContactChip({ label, href, children }) {
  if (!children) return null;
  return (
    <a
      href={href}
      target={href?.startsWith("http") ? "_blank" : undefined}
      rel="noreferrer"
      className="inline-flex items-center gap-1 rounded-md bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-300 transition hover:bg-amber-500/20"
    >
      {label}: {children}
    </a>
  );
}

function VenueCard({ v }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 transition hover:border-amber-500/40">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold text-white">{v.name}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
            <span className="rounded-full bg-slate-800 px-2 py-0.5 font-medium text-slate-300">
              {v.category}
            </span>
            {v.location && <span>{v.location}</span>}
          </div>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        <ContactChip label="phone" href={v.contact?.phone && `tel:${v.contact.phone}`}>
          {v.contact?.phone}
        </ContactChip>
        <ContactChip label="email" href={v.contact?.email && `mailto:${v.contact.email}`}>
          {v.contact?.email}
        </ContactChip>
        <ContactChip label="web" href={v.contact?.website}>
          {v.contact?.website?.replace(/^https?:\/\/(www\.)?/, "").slice(0, 28)}
        </ContactChip>
      </div>
    </div>
  );
}

function IndividualCard({ p }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 transition hover:border-rose-500/40">
      <div className="flex items-center justify-between gap-3">
        <h3 className="truncate font-semibold text-white">{p.name}</h3>
        <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[11px] font-medium text-slate-300">
          {p.platform}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        <ContactChip label="email" href={p.contact?.email && `mailto:${p.contact.email}`}>
          {p.contact?.email}
        </ContactChip>
        <a
          href={p.source_url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 rounded-md bg-slate-800 px-2 py-0.5 text-[11px] font-medium text-slate-400 hover:text-white"
        >
          source ↗
        </a>
      </div>
    </div>
  );
}

export default function B2CSection({ venues, individuals }) {
  function exportB2C() {
    const rows = [
      ...venues.map((v) => ({
        type: "venue", name: v.name, detail: v.category,
        location: v.location || "", phone: v.contact?.phone || "",
        email: v.contact?.email || "",
        link: v.contact?.website || v.source_url || "",
      })),
      ...individuals.map((p) => ({
        type: "individual", name: p.name, detail: p.platform,
        location: "", phone: "", email: p.contact?.email || "",
        link: p.source_url || "",
      })),
    ];
    downloadCsv("leadlens_b2c_leads.csv", rows, [
      { label: "Type", get: (r) => r.type },
      { label: "Name", get: (r) => r.name },
      { label: "Category/Platform", get: (r) => r.detail },
      { label: "Location", get: (r) => r.location },
      { label: "Phone", get: (r) => r.phone },
      { label: "Email", get: (r) => r.email },
      { label: "Link", get: (r) => r.link },
    ]);
  }
  return (
    <section id="b2c" className="scroll-mt-32">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <SectionHeader
          index="3"
          title="B2C Reach"
          subtitle="Public venues your audience visits, and public contacts — for partnership, promo and outreach"
          count={venues.length + individuals.length}
          tone="amber"
        />
        {venues.length + individuals.length > 0 && (
          <ExportButton
            onClick={exportB2C}
            count={venues.length + individuals.length}
            tone="amber"
          />
        )}
      </div>
      <p className="mb-4 text-xs text-slate-500">
        Best-effort, public-web data only — no private individuals' data is
        scraped. Always verify a contact before outreach.
      </p>

      <h3 className="mb-3 text-sm font-bold text-slate-300">
        Venues ({venues.length})
      </h3>
      {venues.length ? (
        <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {venues.map((v, i) => (
            <VenueCard key={v.name + i} v={v} />
          ))}
        </div>
      ) : (
        <div className="mb-6">
          <EmptyState>No local venues surfaced — try adding a city to sharpen this.</EmptyState>
        </div>
      )}

      <h3 className="mb-3 text-sm font-bold text-slate-300">
        Public contacts ({individuals.length})
      </h3>
      {individuals.length ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {individuals.map((p, i) => (
            <IndividualCard key={p.name + i} p={p} />
          ))}
        </div>
      ) : (
        <EmptyState>No self-published public contacts found for this niche/location.</EmptyState>
      )}
    </section>
  );
}
