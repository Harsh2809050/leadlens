const TABS = [
  { id: "competitors", label: "Competitors" },
  { id: "b2b", label: "B2B" },
  { id: "b2c", label: "B2C" },
  { id: "report", label: "Report" },
  { id: "sources", label: "Sources" },
];

export default function TabNav() {
  function jump(id) {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  return (
    <div className="sticky top-[73px] z-10 -mx-6 mb-6 border-b border-slate-800/80 bg-slate-950/90 px-6 backdrop-blur">
      <div className="mx-auto flex max-w-6xl gap-1 overflow-x-auto py-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => jump(t.id)}
            className="whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-400 transition hover:bg-slate-800/60 hover:text-white"
          >
            {t.label}
          </button>
        ))}
      </div>
    </div>
  );
}
