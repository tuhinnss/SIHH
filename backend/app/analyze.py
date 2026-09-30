import logging

from app import tender
from app.llm import LLMUnavailable
from app.recommender import Recommender

log = logging.getLogger("kalamkaar.analyze")
MAX_ITEMS = 40


def analyze_pdf(pdf_bytes: bytes, filename: str, rec: Recommender, linter, max_items: int = MAX_ITEMS,
                offset: int = 0) -> dict:
    """Analyses items[offset:offset + max_items]; `next_offset` (or None) fetches the next page."""
    text, pages, scanned = tender.extract_text(pdf_bytes)
    warning = (f"{scanned} of {pages} page(s) are scanned images without a text layer, so their line items "
               "could not be read (OCR is not supported yet). Check those pages by hand or upload a "
               "text-based PDF.") if scanned else None
    items, method = tender.gem_items(text), "gem"
    if not items:
        items, method = tender.split_items(text), "heuristic"
    if len(items) < 2 and method != "gem" and rec.llm and rec.llm.providers:
        try:
            llm_items = tender.llm_split(text, rec.llm)
            if len(llm_items) > len(items):
                items, method = llm_items, "llm"
        except (LLMUnavailable, KeyError, ValueError, TypeError):
            pass
    if len(items) < 2 and method != "gem":
        items = tender.paragraph_split(text) or items
        method = "paragraph"
    end = offset + max_items
    truncated = len(items) > end
    out_items = []
    page = items[offset:end]
    for i, it, recs in zip(range(offset + 1, end + 1), page, rec.recommend_many(page, top_k=5)):
        cards = recs["results"]
        primary = next((c for c in cards if c["relevance"] == "primary"), None)
        flags, cited = linter.lint_item(it, primary)
        out_items.append({"index": i, "text": it, "cited": cited, "flags": flags,
                          "recommendations": cards[:3], "llm_used": recs["llm_used"]})
    counts = {"red": 0, "amber": 0}
    for it in out_items:
        for f in it["flags"]:
            counts[f["severity"]] += 1
    return {"filename": filename, "pages": pages, "scanned_pages": scanned, "warning": warning,
            "split_method": method, "truncated": truncated,
            "total_items_found": len(items), "offset": offset, "next_offset": end if truncated else None,
            "items": out_items, "summary": counts,
            "disclaimer": "Prototype. Checks are against an older archive catalogue; verify on BIS "
                          "Know Your Standards."}
