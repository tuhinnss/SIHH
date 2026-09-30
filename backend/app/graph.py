"""Allied-standards graph: stored edges + derived same_series, version/supersession info."""
import json
import sqlite3
from collections import defaultdict

from app.catalogue import CatalogueIndex, _split_key
from app.citations import extract_citations
from app.config import DATA, DB_PATH

OUT_TYPES = ("normative_ref", "test_method", "terminology", "scope_ref")
ORDER = {"test_method": 0, "normative_ref": 1, "terminology": 2, "scope_ref": 3, "same_series": 4}


def key_label(key: str) -> str:
    """'IS-12235-P5-S1' -> 'IS 12235 (Part 5) (Sec 1)' (only for keys not in the catalogue)."""
    parts = key.split("-")
    head = [p for p in parts if not (p.startswith("P") and p[1:].isalnum() and p != parts[0]
                                     and parts.index(p) > 1 and any(c.isdigit() for c in p))]
    num_idx = next((i for i, p in enumerate(parts) if p and p[0].isdigit()), 1)
    label = "/".join(parts[:num_idx]) + " " + parts[num_idx]
    for p in parts[num_idx + 1:]:
        if p.startswith("P"):
            label += f" (Part {p[1:]})"
        elif p.startswith("S"):
            label += f" (Sec {p[1:]})"
    return label


class Graph:
    def __init__(self, cat: CatalogueIndex, edges: list[tuple[str, str, str]], meta: dict | None = None):
        self.cat = cat
        self.out: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self.inn: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for s, d, t in edges:
            self.out[s].append((d, t))
            self.inn[d].append((s, t))
        self.n_edges = len(edges)
        self.meta = meta or {}            # key -> {status, committee, scope_snippet}
        self.by_number: dict[str, list[str]] = defaultdict(list)
        for k in cat.entries:
            self.by_number[_split_key(k)[0]].append(k)

    @classmethod
    def from_sqlite(cls, cat: CatalogueIndex, path=DB_PATH) -> "Graph":
        db = sqlite3.connect(path)
        edges = db.execute("select src_key,dst_key,edge_type from edges").fetchall()
        meta: dict[str, dict] = {}
        for key, ident, snip in db.execute("select key,identifier,scope_snippet from standards where scope_snippet is not null"):
            meta.setdefault(key, {})["scope_snippet"] = snip
            meta[key]["identifier"] = ident
        db.close()
        p = DATA / "refs_extracted.jsonl"
        if p.exists():
            ident_key = {v.get("identifier"): k for k, v in meta.items()}
            for line in open(p, encoding="utf-8"):
                r = json.loads(line)
                k = ident_key.get(r["identifier"])
                if k and r.get("ok"):
                    meta[k].update(status=r.get("status"), committee=r.get("committee"))
        return cls(cat, [tuple(e) for e in edges], meta)

    # -- lookups ------------------------------------------------------------
    def find_key(self, text: str) -> str | None:
        text = text.strip()
        up = text.upper().replace(" ", "-")
        if up in self.cat.entries:
            return up
        for c in extract_citations(text):
            e = self.cat.resolve(c)
            if e:
                return e.key
        for k, e in self.cat.entries.items():
            if e.is_number.lower() == text.lower():
                return k
        return None

    def _node(self, key: str) -> dict:
        e = self.cat.entries.get(key)
        return {"key": key, "is_number": e.is_number if e else key_label(key),
                "title": e.title if e else None, "year": e.latest_year if e else None,
                "in_catalogue": e is not None}

    def series(self, key: str) -> list[str]:
        num, part, sec = _split_key(key)
        return sorted(k for k in self.by_number.get(num, []) if k != key and (part or _split_key(k)[1]))

    def allied(self, key: str, limit: int = 8) -> list[dict]:
        seen, items = set(), []
        for dst, t in self.out.get(key, []):
            if t in OUT_TYPES and dst in self.cat.entries and dst not in seen:
                seen.add(dst)
                items.append({**self._node(dst), "edge_type": t})
        for k in self.series(key):
            if k not in seen:
                seen.add(k)
                items.append({**self._node(k), "edge_type": "same_series"})
        items.sort(key=lambda i: (ORDER[i["edge_type"]], i["is_number"]))
        return items[:limit]

    def supersedes_info(self, key: str) -> str | None:
        older = [d for d, t in self.out.get(key, []) if t == "supersedes"]
        newer = [s for s, t in self.inn.get(key, []) if t == "supersedes"]
        bits = []
        if older:
            bits.append("Supersedes " + ", ".join(self._node(k)["is_number"] for k in older))
        if newer:
            bits.append("Superseded by " + ", ".join(self._node(k)["is_number"] for k in newer)
                        + " (per our records; verify on BIS)")
        return "; ".join(bits) or None

    def detail(self, key: str, max_nodes: int = 40) -> dict:
        e = self.cat.entries[key]
        nodes = {key: {**self._node(key), "center": True}}
        links = []

        def link(a, b, t):
            for k in (a, b):
                nodes.setdefault(k, self._node(k))
            links.append({"source": a, "target": b, "type": t})

        for dst, t in self.out.get(key, []):
            link(key, dst, t)
        for src, t in self.inn.get(key, []):
            if len(nodes) < max_nodes:
                link(src, key, t)
        for k in self.series(key)[:12]:
            link(key, k, "same_series")
        m = self.meta.get(key, {})
        return {"key": key, "is_number": e.is_number, "title": e.title, "latest_year": e.latest_year,
                "editions": sorted(e.years), "source_url": e.source_url,
                "scope_snippet": m.get("scope_snippet"), "status": m.get("status"),
                "committee": m.get("committee"), "supersedes_info": self.supersedes_info(key),
                "allied": self.allied(key, limit=30),
                "referenced_by": len([1 for s, t in self.inn.get(key, []) if t != "supersedes"]),
                "graph": {"nodes": list(nodes.values()), "links": links}}
