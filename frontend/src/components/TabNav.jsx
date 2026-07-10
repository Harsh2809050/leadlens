import { useEffect, useState } from "react";

const TABS = [
  { id: "competitors", label: "Competitors" },
  { id: "b2b", label: "B2B" },
  { id: "b2c", label: "B2C" },
  { id: "report", label: "Report" },
  { id: "sources", label: "Sources" },
];

export default function TabNav() {
  const [active, setActive] = useState("competitors");

  useEffect(() => {
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) setActive(e.target.id);
        }
      },
      { rootMargin: "-35% 0px -60% 0px" }
    );
    TABS.forEach((t) => {
      const el = document.getElementById(t.id);
      if (el) obs.observe(el);
    });
    return () => obs.disconnect();
  }, []);

  function jump(id) {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div className="sticky top-[65px] z-10 -mx-6 mb-6 border-b border-slate-800/80 bg-slate-950/90 px-6 backdrop-blur">
      <div className="mx-auto flex max-w-6xl gap-1 overflow-x-auto py-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => jump(t.id)}
            className={`whitespace-nowrap rounded-lg px-3.5 py-1.5 font-mono text-xs font-semibold transition ${
              active === t.id
                ? "bg-indigo-600/20 text-indigo-300 shadow-[inset_0_-2px_0_0] shadow-indigo-500"
                : "text-slate-400 hover:bg-slate-800/60 hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
    </div>
  );
}
