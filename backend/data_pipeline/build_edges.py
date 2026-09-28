"""Turn extraction output + catalogue titles into the `edges` table and scope snippets.

Edge types: supersedes (src = newer, dst = older; dst may be absent from the catalogue),
normative_ref, test_method (target title is a test-method standard), terminology (target title
has Glossary/Terminology/Vocabulary), scope_ref (named in the Scope clause only).
same_series is derived on the fly from the catalogue (same IS number, other parts).
Run after fetch_catalogue (which recreates the DB) and before build_index.
"""
import json
import re
import sqlite3

from sqlmodel import Session, SQLModel, create_engine

from app.catalogue import CatalogueIndex
from app.citations import Citation
from app.config import DB_PATH
from app.models import EdgeRow
from data_pipeline.common import ROOT
from data_pipeline.refs_parsing import find_supersedes, trim_scope

_TEST = re.compile(r"methods?\s+(?:of|for)\s+(?:test|testing|sampling)|test\s+methods?|methods?\s+of\s+(?:chemical\s+)?analysis|testing", re.I)
_TERM = re.compile(r"glossary|terminology|vocabulary", re.I)


def classify(title: str) -> str:
    if _TERM.search(title):
        return "terminology"
    if _TEST.search(title):
        return "test_method"
    return "normative_ref"


_GENERIC = {"specification", "specifications", "requirements", "general", "part", "section", "indian",
            "standard", "standards", "code", "practice", "methods", "method", "test", "guide", "guidelines",
            "with", "from", "used", "using", "based"}


def _words(title: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", (title or "").lower()) if w not in _GENERIC}


def plausible(src_title: str, dst_title: str) -> bool:
    """Foreword prose is noisy: a resolved superseded standard must share a subject word with the new one."""
    return bool(_words(src_title) & _words(dst_title))


def _cit(d: dict) -> Citation:
    return Citation(d["key"], d["key"], d["number"], d.get("part"), d.get("section"), d.get("year"), ())


def main() -> None:
    SQLModel.metadata.create_all(create_engine(f"sqlite:///{DB_PATH}"))
    cat = CatalogueIndex.from_sqlite()
    db = sqlite3.connect(DB_PATH)
    id_key = {i: k for i, k in db.execute("select identifier,key from standards")}
    edges: dict[tuple, dict] = {}

    def add(src, dst, etype, source):
        if src != dst:
            edges.setdefault((src, dst, etype), {"src_key": src, "dst_key": dst, "edge_type": etype, "source": source})

    # 1. supersedes named in catalogue titles (whole catalogue)
    for key, title in db.execute("select key,title from standards"):
        for s in find_supersedes(title):
            add(key, s["key"], "supersedes", "title")

    # 2. extraction results (subset)
    stats = {"records": 0, "ok": 0, "refs": 0, "refs_resolved": 0, "scope_only": 0, "foreword_supersedes": 0}
    snippets: dict[str, str] = {}
    path = ROOT / "data" / "refs_extracted.jsonl"
    for line in (open(path) if path.exists() else []):
        rec = json.loads(line)
        stats["records"] += 1
        src = id_key.get(rec["identifier"])
        if not (rec.get("ok") and src):
            continue
        stats["ok"] += 1
        if rec.get("scope_snippet"):
            snippets[rec["identifier"]] = trim_scope(rec["scope_snippet"])
        ref_keys = set()
        for r in rec.get("refs", []):
            stats["refs"] += 1
            e = cat.resolve(_cit(r))
            if e and e.key != src:
                stats["refs_resolved"] += 1
                ref_keys.add(e.key)
                add(src, e.key, classify(e.title), "annex_or_references")
        for r in rec.get("scope_refs", []):
            e = cat.resolve(_cit(r))
            if e and e.key != src and e.key not in ref_keys:
                stats["scope_only"] += 1
                add(src, e.key, "scope_ref", "scope")
        for s in rec.get("supersedes", []):
            e = cat.resolve(_cit(s), exact_only=True)
            if e and not plausible(cat.entries[src].title, e.title):
                stats["foreword_rejected"] = stats.get("foreword_rejected", 0) + 1
                continue
            dst = e.key if e else s["key"]
            if dst != src:
                stats["foreword_supersedes"] += 1
                add(src, dst, "supersedes", "foreword")

    engine = create_engine(f"sqlite:///{DB_PATH}")
    with Session(engine) as s:
        s.exec(EdgeRow.__table__.delete())
        for e in edges.values():
            s.add(EdgeRow(**e))
        s.commit()
    db.execute("update standards set scope_snippet=null")
    db.executemany("update standards set scope_snippet=? where identifier=?",
                   [(v, k) for k, v in snippets.items()])
    db.commit()
    db.close()
    by_type: dict[str, int] = {}
    for e in edges.values():
        by_type[e["edge_type"]] = by_type.get(e["edge_type"], 0) + 1
    print(stats)
    print("edges:", len(edges), by_type, "| scope snippets:", len(snippets))


if __name__ == "__main__":
    main()
