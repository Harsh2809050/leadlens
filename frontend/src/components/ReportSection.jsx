import { SectionHeader } from "./ui.jsx";

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

export default function ReportSection({ report }) {
  return (
    <section id="report" className="scroll-mt-32">
      <SectionHeader
        index="4"
        title="Business Intelligence Report"
        subtitle="Analyst view built from competitor, positioning and trend data"
        tone="indigo"
      />
      {report?.summary && (
        <div className="mb-5 rounded-xl border border-indigo-500/25 bg-indigo-500/5 p-6">
          <p className="mb-1.5 text-[11px] font-bold uppercase tracking-widest text-indigo-400">
            Executive summary
          </p>
          <p className="text-sm leading-relaxed text-slate-300">
            {report.summary}
          </p>
        </div>
      )}
      <div className="grid gap-5 lg:grid-cols-2">
        <ReportBlock
          icon="▲"
          tone="growth"
          title="3 things that can grow this company"
          items={report?.growth || []}
        />
        <ReportBlock
          icon="▼"
          tone="risk"
          title="3 things that can kill it"
          items={report?.risks || []}
        />
      </div>
    </section>
  );
}
