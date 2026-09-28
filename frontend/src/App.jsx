import { useState } from "react";

const EXAMPLES = [
  "PVC pipes for drinking water supply",
  "TMT steel bars for RCC",
  "LED street light 60W",
  "पीने के पानी के लिए पीवीसी पाइप",
];

export default function App() {
  const [text, setText] = useState("");
  const [results, setResults] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

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
          <h1 className="text-2xl font-bold">SpecSure</h1>
          <span className="text-sm text-blue-100">Indian Standards recommender for procurement specifications</span>
        </div>
      </header>

      <main className="max-w-4xl w-full mx-auto px-4 py-8 flex-1">
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

        {results && (
          <ol className="mt-8 space-y-3">
            {results.map((r, i) => (
              <li key={r.is_number + r.year} className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-slate-400 w-5">{i + 1}.</span>
                  <span className="bg-navy text-white text-sm font-semibold px-2 py-0.5 rounded">{r.is_number}</span>
                  <span className="text-sm text-slate-500">{r.year ?? "year unknown"}</span>
                  <span className="text-xs bg-accent/30 border border-accent rounded px-2 py-0.5" title="Edition per our archive snapshot">
                    as per catalogue — verify on BIS
                  </span>
                </div>
                <p className="mt-2 font-medium">{r.title}</p>
                <a href={r.source_url} target="_blank" rel="noreferrer" className="text-sm text-navy underline">Source</a>
              </li>
            ))}
          </ol>
        )}
      </main>

      <footer className="text-center text-xs text-slate-500 py-4 border-t border-slate-200">
        Prototype — verify on BIS Know Your Standards. Catalogue is an older archive snapshot.
      </footer>
    </div>
  );
}
