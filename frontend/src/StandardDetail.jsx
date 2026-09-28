import { useEffect, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";

export const EDGE_STYLE = {
  normative_ref: { label: "Normative reference", color: "#1f4a86" },
  test_method: { label: "Test method", color: "#0f8a5f" },
  terminology: { label: "Terminology", color: "#7b4ea3" },
  scope_ref: { label: "Named in scope", color: "#8a6d00" },
  same_series: { label: "Same series (other parts)", color: "#64748b" },
  supersedes: { label: "Supersedes", color: "#c62828" },
};

export default function StandardDetail({ query, onOpen }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const box = useRef(null);
  const fg = useRef(null);
  const [width, setWidth] = useState(700);

  useEffect(() => {
    setData(null); setError(null);
    fetch(`/api/standard/${encodeURIComponent(query)}`)
      .then(async (r) => { if (!r.ok) throw new Error((await r.json()).detail); return r.json(); })
      .then(setData).catch((e) => setError(e.message));
  }, [query]);

  useEffect(() => { if (box.current) setWidth(box.current.clientWidth); }, [data]);
  useEffect(() => {
    if (!data || !fg.current) return;
    fg.current.d3Force("charge").strength(-260);
    fg.current.d3Force("link").distance(95);
  }, [data]);

  if (error) return <p className="text-red-700">{error}</p>;
  if (!data) return <p className="text-slate-500">Loading…</p>;
  const g = data.graph;
  const hasEdges = g.links.length > 0;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="bg-navy text-white font-semibold px-2 py-0.5 rounded">{data.is_number}</span>
        <span className="text-slate-500">latest edition in our catalogue: {data.latest_year ?? "unknown"}</span>
        {data.editions.length > 1 && <span className="text-xs text-slate-500">(editions: {data.editions.join(", ")})</span>}
        {data.status && <span className="text-xs border border-slate-300 rounded px-2 py-0.5">archive status: {data.status}</span>}
      </div>
      <h2 className="mt-2 text-xl font-semibold">{data.title}</h2>
      {data.supersedes_info && <p className="mt-2 text-sm bg-amber-50 border border-amber-300 rounded px-3 py-2">{data.supersedes_info}</p>}
      {data.scope_snippet && <p className="mt-3 text-sm text-slate-600"><b>Scope (extract):</b> {data.scope_snippet}…</p>}
      <p className="mt-2 text-sm"><a className="text-navy underline" href={data.source_url} target="_blank" rel="noreferrer">Official/archive source</a> · verify the current edition on BIS Know Your Standards</p>

      <h3 className="mt-6 font-semibold">Allied standards graph</h3>
      <div className="flex flex-wrap gap-3 text-xs my-2">
        {Object.entries(EDGE_STYLE).map(([k, v]) => (
          <span key={k} className="flex items-center gap-1"><i className="inline-block w-3 h-1" style={{ background: v.color }} />{v.label}</span>))}
      </div>
      <div ref={box} className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        {hasEdges ? (
          <ForceGraph2D
            ref={fg}
            cooldownTicks={120}
            onEngineStop={() => fg.current && fg.current.zoomToFit(400, 60)}
            graphData={{ nodes: g.nodes.map((n) => ({ ...n, id: n.key })), links: g.links.map((l) => ({ ...l })) }}
            width={width} height={420}
            nodeLabel={(n) => `${n.is_number}${n.title ? " — " + n.title : " (not in catalogue)"}`}
            linkColor={(l) => EDGE_STYLE[l.type]?.color || "#999"}
            linkDirectionalArrowLength={4} linkDirectionalArrowRelPos={1}
            nodeCanvasObject={(n, ctx, scale) => {
              const r = n.center ? 7 : 5;
              ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
              ctx.fillStyle = n.center ? "#ffc601" : n.in_catalogue ? "#1f4a86" : "#b0b7c3"; ctx.fill();
              if (n.center) { ctx.strokeStyle = "#1f4a86"; ctx.lineWidth = 1.5; ctx.stroke(); }
              ctx.font = `${11 / scale}px sans-serif`; ctx.fillStyle = "#1e293b"; ctx.textAlign = "center";
              ctx.fillText(n.is_number, n.x, n.y + r + 8 / scale);
            }}
            onNodeClick={(n) => n.in_catalogue && n.key !== data.key && onOpen(n.is_number)}
          />
        ) : <p className="p-6 text-slate-500 text-sm">No relations stored for this standard yet (references were extracted for a subset of about 300 standards).</p>}
      </div>

      <h3 className="mt-6 font-semibold">Related standards</h3>
      <ul className="mt-2 space-y-1 text-sm">
        {data.allied.map((a) => (
          <li key={a.key + a.edge_type}>
            <span className="text-xs mr-2 px-1.5 py-0.5 rounded border" style={{ borderColor: EDGE_STYLE[a.edge_type].color, color: EDGE_STYLE[a.edge_type].color }}>{EDGE_STYLE[a.edge_type].label}</span>
            <button className="text-navy underline" onClick={() => onOpen(a.is_number)}>{a.is_number}</button> {a.year && <span className="text-slate-500">({a.year})</span>} — {a.title}
          </li>))}
        {data.allied.length === 0 && <li className="text-slate-500">None recorded.</li>}
      </ul>
      {data.referenced_by > 0 && <p className="mt-3 text-sm text-slate-500">Referenced by {data.referenced_by} other standard(s) in our extracted subset.</p>}
    </div>
  );
}
