import { useState } from "react";
import TenderCheck from "./TenderCheck.jsx";
import StandardDetail, { EDGE_STYLE } from "./StandardDetail.jsx";
import About from "./About.jsx";

const EXAMPLES = [
  "PVC pipes for drinking water supply",
  "TMT steel bars for RCC",
  "LED street light 60W",
  "पीने के पानी के लिए पीवीसी पाइप",
];

export default function App() {
  const [tab, setTab] = useState("search");
  const [detail, setDetail] = useState(null);
  const openDetail = (q) => { setDetail(q); setTab("detail"); window.scrollTo(0, 0); };
  const [text, setText] = useState("");
  const [results, setResults] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [llmUsed, setLlmUsed] = useState(null);
  const [copied, setCopied] = useState(null);

  async function copyClause(r) {
    try {
      await navigator.clipboard.writeText(r.clause);
      setCopied(r.is_number);
      setTimeout(() => setCopied(null), 1500);
    } catch {
      window.prompt("Copy the clause:", r.clause);
    }
  }

  async function search(q = text) {
    if (!q.trim()) return;
    setText(q);
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: q, top_k: 10 }),
      });
      if (!r.ok) throw new Error(`API ${r.status}`);
      setLlmUsed(r.headers.get("X-LLM-Used") === "true");
      setResults(await r.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-navy text-white border-b-4 border-accent">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-baseline gap-3">
          <h1 className="text-2xl font-bold">Kalamkaar</h1>
          <span className="text-sm text-blue-100">Indian Standards recommender for procurement specifications</span>
        </div>
        <nav className="max-w-4xl mx-auto px-4 flex gap-1 text-sm">
          {[["search", "Search"], ["tender", "Tender Check"], ...(detail ? [["detail", "Standard"]] : []), ["about", "About"]].map(([id, label]) => (
            <button key={id} onClick={() => setTab(id)}
              className={`px-4 py-1.5 rounded-t ${tab === id ? "bg-slate-50 text-navy font-semibold" : "text-blue-100 hover:text-white"}`}>{label}</button>
          ))}
        </nav>
      </header>

      <main className={`${tab === "tender" ? "max-w-6xl" : "max-w-4xl"} w-full mx-auto px-4 py-8 flex-1`}>
        {tab === "tender" ? <TenderCheck /> : tab === "about" ? <About /> : tab === "detail" ? <StandardDetail query={detail} onOpen={openDetail} /> : <>
        <form onSubmit={(e) => { e.preventDefault(); search(); }}>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            placeholder="Paste a product description or specification line…"
            className="w-full rounded-lg border border-slate-300 p-4 text-lg focus:outline-none focus:ring-2 focus:ring-navy"
          />
          <div className="mt-3 flex flex-wrap gap-2 items-center">
            <button disabled={busy} className="bg-navy text-white px-6 py-2 rounded-lg font-semibold hover:bg-blue-900 disabled:opacity-60">
              {busy ? "Searching…" : "Find standards"}
            </button>
            {EXAMPLES.map((ex) => (
              <button type="button" key={ex} onClick={() => search(ex)}
                className="text-sm border border-slate-300 bg-white rounded-full px-3 py-1 hover:border-navy">
                {ex}
              </button>
            ))}
          </div>
        </form>

        {error && <p className="mt-6 text-red-700">Could not reach the API ({error}).</p>}

        {results && llmUsed === false && (
          <p className="mt-6 text-sm bg-amber-50 border border-amber-300 rounded px-3 py-2">
            AI ranking is unavailable, so these are plain keyword/semantic matches without reasons.
          </p>
        )}

        {results && (
          <ol className="mt-8 space-y-3">
            {results.map((r, i) => (
              <li key={r.is_number + r.year} className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-slate-400 w-5">{i + 1}.</span>
                  <button onClick={() => openDetail(r.is_number)} title="Open details and graph" className="bg-navy text-white text-sm font-semibold px-2 py-0.5 rounded hover:bg-blue-900">{r.is_number}</button>
                  <span className={`text-xs px-2 py-0.5 rounded border ${r.relevance === "primary" ? "border-navy text-navy" : "border-slate-300 text-slate-500"}`}>
                    {r.relevance}
                  </span>
                  <span className="text-sm text-slate-500">{r.year ?? "year unknown"}</span>
                  <span className="text-xs bg-accent/30 border border-accent rounded px-2 py-0.5" title="Edition per our archive snapshot">
                    as per catalogue — verify on BIS
                  </span>
                </div>
                <p className="mt-2 font-medium">{r.title}</p>
                {r.reason && <p className="mt-1 text-sm text-slate-600">{r.reason}</p>}
                {r.supersedes_info && <p className="mt-1 text-xs bg-amber-50 border border-amber-300 rounded px-2 py-1 inline-block">{r.supersedes_info}</p>}
                {r.certification && <p className="mt-1 text-xs bg-green-50 border border-green-300 rounded px-2 py-1 inline-block">Certification: {r.certification.scheme} (verified {r.certification.last_verified || "date n/a"})</p>}
                {r.allied?.length > 0 && (
                  <div className="mt-2 text-xs space-y-1">
                    {Object.keys(EDGE_STYLE).map((t) => {
                      const items = r.allied.filter((a) => a.edge_type === t);
                      return items.length ? (
                        <div key={t} className="flex flex-wrap items-center gap-1">
                          <span className="text-slate-500 w-40">{EDGE_STYLE[t].label}:</span>
                          {items.map((a) => (
                            <button key={a.key} onClick={() => openDetail(a.is_number)} title={a.title}
                              className="border rounded-full px-2 py-0.5 hover:bg-slate-100" style={{ borderColor: EDGE_STYLE[t].color, color: EDGE_STYLE[t].color }}>{a.is_number}</button>))}
                        </div>) : null;
                    })}
                  </div>)}
                <div className="mt-2 flex items-center gap-4 text-sm">
                  <button onClick={() => copyClause(r)} className="border border-navy text-navy rounded px-2 py-0.5 hover:bg-navy hover:text-white">
                    {copied === r.is_number ? "Copied ✓" : "Copy tender clause"}
                  </button>
                  <a href={r.source_url} target="_blank" rel="noreferrer" className="text-navy underline">Source</a>
                  {llmUsed && <span className="text-slate-400">confidence {Math.round(r.confidence * 100)}%</span>}
                </div>
              </li>
            ))}
          </ol>
        )}
        </>}
      </main>

      <footer className="text-center text-xs text-slate-500 py-4 border-t border-slate-200">
        Prototype — verify on BIS Know Your Standards. Catalogue is an older archive snapshot.
      </footer>
    </div>
  );
}
