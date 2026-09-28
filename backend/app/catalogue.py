"""In-memory view of the SQLite catalogue for citation resolution and version checks."""
import sqlite3
from dataclasses import dataclass

from sqlmodel import SQLModel, create_engine

from app import models  # noqa: F401  (registers tables)
from app.citations import Citation
from app.config import DB_PATH


@dataclass
class Entry:
    key: str
    is_number: str
    title: str
    latest_year: int | None
    years: list[int]
    source_url: str


class CatalogueIndex:
    def __init__(self, entries: dict[str, Entry], superseded_by: dict[str, list[str]] | None = None):
        self.entries = entries
        self.superseded_by = superseded_by or {}
        self._by_np: dict[tuple, list[str]] = {}
        for k in entries:
            n, p, s = _split_key(k)
            self._by_np.setdefault((n, p, s), []).append(k)

    @classmethod
    def from_sqlite(cls, path=DB_PATH) -> "CatalogueIndex":
        SQLModel.metadata.create_all(create_engine(f"sqlite:///{path}"))  # ensures edges table
        db = sqlite3.connect(path)
        rows = db.execute("select key,is_number,title,year,source_url,flags from standards").fetchall()
        entries: dict[str, Entry] = {}
        for key, num, title, year, url, flags in rows:
            e = entries.get(key)
            if e is None:
                entries[key] = e = Entry(key, num, title, None, [], url)
            if year:
                e.years.append(year)
            if not flags and (year or 0) >= (e.latest_year or 0):
                e.title, e.source_url = title, url  # prefer newest plain-English copy
        for e in entries.values():
            e.latest_year = max(e.years) if e.years else None
        sup: dict[str, list[str]] = {}
        for src, dst in db.execute("select src_key,dst_key from edges where edge_type='supersedes'"):
            sup.setdefault(dst, []).append(src)
        db.close()
        return cls(entries, sup)

    def resolve(self, c: Citation, exact_only: bool = False) -> Entry | None:
        """Exact key first. Fallback ignores the joint prefix (IS 60947-2 vs IS/IEC 60947-2) but only
        for long numbers (IEC/ISO style, >=5 digits): short numbers collide with unrelated plain IS
        numbers (IS 691 is not IS/IEC 691)."""
        if c.key in self.entries:
            return self.entries[c.key]
        if exact_only or len(c.number) < 5:
            return None
        cands = self._by_np.get((c.number, c.part, c.section), [])
        return self.entries[cands[0]] if len(cands) == 1 else None


def _split_key(key: str) -> tuple[str, str | None, str | None]:
    import re
    m = re.match(r"^[A-Z]+(?:-(?:ISO|IEC|IEEE|TR|TS|PAS))*-([^-]+)(?:-P([^-]+))?(?:-S([^-]+))?", key)
    return (m[1], m[2], m[3]) if m else (key, None, None)
