import { useEffect, useState } from "react";

export default function About() {
  const [s, setS] = useState(null);
  useEffect(() => { fetch("/api/stats").then((r) => r.json()).then(setS).catch(() => setS({})); }, []);
  const Stat = ({ label, value }) => (
    <div className="bg-white border border-slate-200 rounded-lg p-4"><div className="text-2xl font-bold text-navy">{value ?? "—"}</div><div className="text-sm text-slate-500">{label}</div></div>);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Catalogue records" value={s?.catalogue_records?.toLocaleString()} />
        <Stat label="Searchable standards" value={s?.retrieval_documents?.toLocaleString()} />
        <Stat label="Relations (edges)" value={s?.edges?.toLocaleString()} />
        <Stat label="Last catalogue sync" value={s?.last_sync} />
      </div>
      {s?.edges_by_type && <p className="text-sm text-slate-600">Edges by type: {Object.entries(s.edges_by_type).map(([k, v]) => `${k} ${v}`).join(" · ")}. Standards with extracted scope text: {s.standards_with_scope_text}. Certification rows: {s.certification_rows}.</p>}
      <section>
        <h2 className="font-semibold text-lg">Data sources</h2>
        <ul className="list-disc ml-6 text-sm mt-1 space-y-1">
          <li>Catalogue: Internet Archive “gov.in.is.*” collection (metadata only: number, title, edition year).</li>
          <li>Relations: references, scope and supersession extracted from OCR text for a subset of ~300 standards, plus “Superseding …” notes in catalogue titles. Raw texts are not stored.</li>
          <li>Certification: a hand-verified, dated table (<code>certification.csv</code>). Shown only where a row exists.</li>
        </ul>
      </section>
      <section className="bg-amber-50 border border-amber-300 rounded-lg p-4">
        <h2 className="font-semibold">Honest disclaimers</h2>
        <ul className="list-disc ml-6 text-sm mt-1 space-y-1">
          <li>The archive is an <b>older snapshot</b>; many items date from before 2015. “Latest version” means <i>as per our catalogue</i> — verify on BIS Know Your Standards.</li>
          <li>Standard texts belong to the Bureau of Indian Standards; Kalamkaar links to sources and does not republish them.</li>
          <li>Relation coverage is partial (a subset of standards); a missing relation is not proof that none exists.</li>
          <li>AI suggestions are limited to catalogue candidates and validated, but a procurement officer must confirm applicability.</li>
        </ul>
      </section>
    </div>
  );
}
