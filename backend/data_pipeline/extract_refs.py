"""For each standard in data/subset_ids.json: metadata -> OCR text -> scope snippet, referred
standards, supersession. Raw text is held in memory only and discarded (never written to disk).
Results: data/refs_extracted.jsonl (resumable; metadata-only, no standard texts).
--retry-failed re-attempts standards whose download failed earlier."""
import json
import re
import sys
import urllib.parse

from tqdm import tqdm

from data_pipeline.common import ROOT, polite_get_json, polite_get_text
from data_pipeline.refs_parsing import find_refs, find_scope, find_supersedes, scope_refs

OUT = ROOT / "data" / "refs_extracted.jsonl"
SUBSET = ROOT / "data" / "subset_ids.json"


def djvu_name(meta: dict) -> str | None:
    """Main document's OCR text (skip amendment files, which the archive names 'z...')."""
    names = [f["name"] for f in meta.get("files", []) if f["name"].endswith("_djvu.txt")]
    main = [n for n in names if not n.startswith("z")]
    return (main or names or [None])[0]


def parse_status(meta: dict) -> dict:
    d = meta.get("metadata", {}).get("description", "")
    d = " ".join(d) if isinstance(d, list) else d
    grab = lambda label: (m.group(1).strip() or None) if (m := re.search(label + r":</b>\s*([^<]*)", d)) else None  # noqa: E731
    return {"status": grab("Status"), "committee": grab("Committee Designation"),
            "amendments": grab("Number of Amendments")}


def process(identifier: str) -> dict:
    meta = polite_get_json(f"https://archive.org/metadata/{identifier}")
    rec = {"identifier": identifier, **parse_status(meta), "ok": False}
    name = djvu_name(meta)
    if not name:
        rec["error"] = "no_ocr_text"
        return rec
    text = polite_get_text(f"https://archive.org/download/{identifier}/{urllib.parse.quote(name)}")
    if not text:
        rec["error"] = "empty_text"
        return rec
    scope = find_scope(text)
    head = text[:12000]  # foreword lives near the front
    rec.update(ok=True, scope_snippet=scope, refs=find_refs(text), scope_refs=scope_refs(scope),
               supersedes=find_supersedes(head))
    return rec


def main(retry_failed: bool = False) -> None:
    ids = [x["identifier"] for x in json.loads(SUBSET.read_text(encoding="utf-8"))]
    done = set()
    if OUT.exists():
        rows = [json.loads(l) for l in open(OUT, encoding="utf-8")]
        if retry_failed:  # forget failed downloads so they are attempted again
            rows = [r for r in rows if r.get("ok")]
            with open(OUT, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        done = {r["identifier"] for r in rows}
    todo = [i for i in ids if i not in done]
    print(f"{len(done)} done, {len(todo)} to go")
    with open(OUT, "a", encoding="utf-8", newline="\n") as f:
        for ident in tqdm(todo, desc="standards"):
            try:
                rec = process(ident)
            except Exception as e:  # noqa: BLE001 - keep going; record the failure
                rec = {"identifier": ident, "ok": False, "error": type(e).__name__}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()


if __name__ == "__main__":
    main(retry_failed="--retry-failed" in sys.argv)
