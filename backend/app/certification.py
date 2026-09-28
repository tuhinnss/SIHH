"""Certification table (hand-filled data/certification.csv). Shown only when a dated row exists."""
import csv
from datetime import date
from pathlib import Path

from app.config import DATA

FIELDS = ["product", "is_number", "scheme", "order_reference", "effective_date",
          "withdrawn_date", "source_url", "last_verified"]


def _d(s: str) -> date | None:
    try:
        return date.fromisoformat(s.strip())
    except ValueError:
        return None


class CertificationTable:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    @classmethod
    def load(cls, path: Path = DATA / "certification.csv") -> "CertificationTable":
        if not path.exists():
            return cls([])
        with open(path, newline="") as f:
            return cls([r for r in csv.DictReader(f) if (r.get("is_number") or r.get("product"))])

    def active(self, today: date | None = None) -> list[dict]:
        today = today or date.today()
        out = []
        for r in self.rows:
            eff, wd = _d(r.get("effective_date", "")), _d(r.get("withdrawn_date", ""))
            if eff and eff > today:
                continue
            if wd and wd <= today:
                continue
            out.append(r)
        return out

    def for_is(self, is_number: str) -> dict | None:
        for r in self.active():
            if r["is_number"].strip().lower() == is_number.strip().lower():
                return _view(r)
        return None

    def for_text(self, text: str) -> list[dict]:
        low = text.lower()
        return [_view(r) for r in self.active() if r["product"].strip() and r["product"].strip().lower() in low]


def _view(r: dict) -> dict:
    return {k: r.get(k) or None for k in FIELDS if k != "product"} | {"product": r.get("product")}
