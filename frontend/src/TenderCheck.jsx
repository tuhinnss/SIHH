import { useState } from "react";

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function auditHtml(r) {
  const rows = r.items.map((it) => `
    <tr><td>${it.index}</td><td>${esc(it.text)}</td>
    <td>${it.recommendations.map((c) => `<div><b>${esc(c.is_number)}</b> (${esc(c.year ?? "?")}) ${esc(c.title)}</div>`).join("") || "—"}</td>
    <td>${it.flags.map((f) => `<div class="${f.severity}">${f.severity.toUpperCase()}: ${esc(f.message)}</div>`).join("") || "No issues found"}</td></tr>`).join("");
  return `<!doctype html><html><head><meta charset="utf-8"><title>SpecSure audit — ${esc(r.filename)}</title>
  <style>body{font-family:sans-serif;font-size:12px;margin:24px}h1{color:#1f4a86}table{border-collapse:collapse;width:100%}
  td,th{border:1px solid #999;padding:6px;vertical-align:top}th{background:#1f4a86;color:#fff}.red{color:#b00020}.amber{color:#a35a00}
  .note{background:#fff8d6;border:1px solid #ffc601;padding:8px;margin:12px 0}</style></head><body>
  <h1>SpecSure — Tender audit report</h1>
  <p><b>File:</b> ${esc(r.filename)} · ${r.pages} page(s) · ${r.items.length} item(s) analysed${r.truncated ? ` of ${r.total_items_found}` : ""} · <b>${r.summary.red}</b> red / <b>${r.summary.amber}</b> amber flags · generated ${new Date().toLocaleString()}</p>
  <div class="note">${esc(r.disclaimer)}</div>
  <table><tr><th>#</th><th>Line item</th><th>Suggested standards (per our catalogue)</th><th>Linter findings</th></tr>${rows}</table>
  </body></html>`;
}

const chip = { red: "bg-red-100 text-red-800 border-red-300", amber: "bg-amber-100 text-amber-900 border-amber-300" };

export default function TenderCheck() {
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function upload(file) {
    if (!file) return;
    setBusy(true); setError(null); setRes(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await fetch("/api/analyze-tender", { method: "POST", body: fd });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `API ${r.status}`);
      setRes(await r.json());
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  function exportReport() {
    const w = window.open("", "_blank");
    if (!w) { setError("Pop-up blocked — allow pop-ups to export the report."); return; }
    w.document.write(auditHtml(res)); w.document.close(); w.focus(); setTimeout(() => w.print(), 300);
  }

  return (
    <div>
      <label className="block border-2 border-dashed border-slate-300 rounded-lg bg-white p-8 text-center cursor-pointer hover:border-navy">
        <input type="file" accept="application/pdf" className="hidden" onChange={(e) => upload(e.target.files[0])} />
        <span className="font-semibold text-navy">{busy ? "Analysing tender… (this can take a minute)" : "Upload a tender PDF"}</span>
        <span className="block text-sm text-slate-500 mt-1">Line items are extracted, matched to Indian Standards and checked by the Tender Linter.</span>
      </label>
      {error && <p className="mt-4 text-red-700">{error}</p>}
      {res && (
        <div className="mt-6">
          <div className="flex flex-wrap items-center gap-3 mb-3">
            <span className="font-semibold">{res.filename}</span>
            <span className="text-sm text-slate-500">{res.pages} {res.pages === 1 ? "page" : "pages"} · {res.items.length} items ({res.split_method} split)</span>
            <span className={`text-xs border rounded px-2 py-0.5 ${chip.red}`}>{res.summary.red} red</span>
            <span className={`text-xs border rounded px-2 py-0.5 ${chip.amber}`}>{res.summary.amber} amber</span>
            <button onClick={exportReport} className="ml-auto bg-navy text-white text-sm px-4 py-1.5 rounded hover:bg-blue-900">Export audit report</button>
          </div>
          {res.truncated && <p className="text-sm bg-amber-50 border border-amber-300 rounded px-3 py-2 mb-3">Showing the first {res.items.length} of {res.total_items_found} items found.</p>}
          <div className="overflow-x-auto bg-white border border-slate-200 rounded-lg">
            <table className="w-full text-sm">
              <thead className="bg-navy text-white text-left"><tr><th className="p-2 w-8">#</th><th className="p-2">Line item</th><th className="p-2">Suggested standards</th><th className="p-2">Linter flags</th></tr></thead>
              <tbody>
                {res.items.map((it) => (
                  <tr key={it.index} className="border-t border-slate-200 align-top">
                    <td className="p-2 text-slate-400">{it.index}</td>
                    <td className="p-2 max-w-xs">{it.text}</td>
                    <td className="p-2">{it.recommendations.map((c) => (
                      <div key={c.is_number} className="mb-1"><a href={c.source_url} target="_blank" rel="noreferrer" className="font-semibold text-navy underline">{c.is_number}</a> <span className="text-slate-500">{c.year}</span><div className="text-xs text-slate-600">{c.title}</div></div>))}</td>
                    <td className="p-2 space-y-1">{it.flags.length === 0 ? <span className="text-green-700">No issues</span> :
                      it.flags.map((f, i) => <div key={i} className={`text-xs border rounded px-2 py-1 ${chip[f.severity]}`}>{f.message}</div>)}</td>
                  </tr>))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
