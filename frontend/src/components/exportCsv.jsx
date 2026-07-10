// Client-side CSV export — no server round-trip, works offline on cached data.
export function downloadCsv(filename, rows, headers) {
  const esc = (v) => {
    const s = String(v ?? "");
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  const lines = [headers.map((h) => esc(h.label)).join(",")];
  for (const r of rows) {
    lines.push(headers.map((h) => esc(h.get(r))).join(","));
  }
  const blob = new Blob(["﻿" + lines.join("\r\n")], {
    type: "text/csv;charset=utf-8",
  });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

export function ExportButton({ onClick, count, tone = "teal" }) {
  const tones = {
    teal: "border-teal-500/40 text-teal-300 hover:bg-teal-500/10",
    amber: "border-amber-500/40 text-amber-300 hover:bg-amber-500/10",
  };
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${tones[tone]}`}
    >
      <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v12m0 0l-4-4m4 4l4-4M4 20h16" />
      </svg>
      Export CSV ({count})
    </button>
  );
}
