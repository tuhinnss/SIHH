"""Validate the hand-filled data/certification.csv (columns, dates, IS numbers known to the catalogue)."""
import csv
import sys
from datetime import date

from app.catalogue import CatalogueIndex
from app.config import DATA
from app.graph import Graph

REQUIRED = ["product", "is_number", "scheme", "order_reference", "effective_date",
            "withdrawn_date", "source_url", "last_verified"]
SCHEMES = {"ISI/QCO", "CRS", "Hallmarking"}


def check(path=DATA / "certification.csv", graph: Graph | None = None) -> list[str]:
    problems = []
    with open(path, newline="") as f:
        rd = csv.DictReader(f)
        if rd.fieldnames != REQUIRED:
            return [f"header must be exactly: {','.join(REQUIRED)}"]
        for n, r in enumerate(rd, start=2):
            where = f"row {n}"
            if r["scheme"] not in SCHEMES:
                problems.append(f"{where}: scheme must be one of {sorted(SCHEMES)}")
            for col in ("effective_date", "withdrawn_date", "last_verified"):
                v = r[col].strip()
                if v:
                    try:
                        date.fromisoformat(v)
                    except ValueError:
                        problems.append(f"{where}: {col} '{v}' is not YYYY-MM-DD")
            if not r["effective_date"].strip():
                problems.append(f"{where}: effective_date is required")
            if not r["source_url"].startswith("http"):
                problems.append(f"{where}: source_url must be an official link")
            if not r["last_verified"].strip():
                problems.append(f"{where}: last_verified is required (hand-verified dated table)")
            if graph and not graph.find_key(r["is_number"]):
                problems.append(f"{where}: '{r['is_number']}' not found in catalogue")
    return problems


if __name__ == "__main__":
    probs = check(graph=Graph.from_sqlite(CatalogueIndex.from_sqlite()))
    print("\n".join(probs) if probs else "certification.csv OK")
    sys.exit(1 if probs else 0)
