"""Turn REAL tender PDFs (e.g. downloaded from CPPP / GeM) into evaluation rows.

Every line item that cites Indian Standards becomes
    {"query": item text with the citations removed, "gold_is": [cited standards], "lang", "source"}
so the gold labels are what the tender's author cited, never guessed by us. Review the rows (delete
ones where the citation is not about the item itself) before trusting the metrics.
Usage: python -m eval.from_tenders tenders/*.pdf [--out eval/tender_rows.jsonl]
then:  python -m eval.run_eval --file eval/tender_rows.jsonl
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import tender  # noqa: E402
from app.citations import extract_citations, strip_citations  # noqa: E402
from app.lang import detect_lang  # noqa: E402

MIN_QUERY = 15  # shorter leftovers ("Cable", "Item") are not a usable query


def rows_from_text(text: str, source: str) -> list[dict]:
    items = tender.split_items(text)
    if len(items) < 2:
        items = tender.paragraph_split(text) or items
    rows = []
    for i, item in enumerate(items, 1):
        cites = extract_citations(item)
        query = strip_citations(item)
        if cites and len(query) >= MIN_QUERY:
            rows.append({"query": query, "gold_is": [c.raw for c in cites], "lang": detect_lang(query),
                         "source": f"{source}#item{i}"})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--out", default=str(Path(__file__).with_name("tender_rows.jsonl")))
    a = ap.parse_args()
    out = Path(a.out)
    seen = set()
    if out.exists():
        seen = {json.loads(l)["query"] for l in open(out, encoding="utf-8") if l.strip()}
    added = 0
    with open(out, "a", encoding="utf-8", newline="\n") as f:
        for p in map(Path, a.pdfs):
            text, pages, scanned = tender.extract_text(p.read_bytes(), max_chars=None)
            rows = rows_from_text(text, p.name)
            for r in rows:
                if r["query"] not in seen:
                    seen.add(r["query"])
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                    added += 1
            note = f", {scanned} scanned page(s) unreadable" if scanned else ""
            print(f"{p.name}: {pages} pages{note}, {len(rows)} items citing IS")
    print(f"{added} new rows -> {out}\nReview them, then: python -m eval.run_eval --file {out}")


if __name__ == "__main__":
    main()
