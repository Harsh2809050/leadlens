export default function SourcesSection({ sources }) {
  if (!sources?.length) return null;
  return (
    <section id="sources" className="scroll-mt-32 rounded-xl border border-slate-800/80 bg-slate-900/40 p-5">
      <p className="mb-2 text-xs font-bold uppercase tracking-widest text-slate-500">
        Sources consulted ({sources.length})
      </p>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {sources.map((s) => (
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
  );
}
