import logging

from app import tender
from app.llm import LLMUnavailable
from app.recommender import Recommender

log = logging.getLogger("specsure.analyze")
MAX_ITEMS = 40


def analyze_pdf(pdf_bytes: bytes, filename: str, rec: Recommender, linter, max_items: int = MAX_ITEMS,
                offset: int = 0) -> dict:
    """Analyses items[offset:offset + max_items]; `next_offset` (or None) fetches the next page."""
    text, pages = tender.extract_text(pdf_bytes)
    method = "heuristic"
    items = tender.split_items(text)
    if len(items) < 2 and rec.llm and rec.llm.providers:
        try:
            llm_items = tender.llm_split(text, rec.llm)
            if len(llm_items) > len(items):
                items, method = llm_items, "llm"
        except (LLMUnavailable, KeyError, ValueError, TypeError):
            pass
    if len(items) < 2:
        items = tender.paragraph_split(text) or items
        method = "paragraph"
    end = offset + max_items
    truncated = len(items) > end
    out_items = []
    for i, it in enumerate(items[offset:end], offset + 1):
        recs = rec.recommend(it, top_k=5)
        cards = recs["results"]
        primary = next((c for c in cards if c["relevance"] == "primary"), None)
        flags, cited = linter.lint_item(it, primary)
        out_items.append({"index": i, "text": it, "cited": cited, "flags": flags,
                          "recommendations": cards[:3], "llm_used": recs["llm_used"]})
    counts = {"red": 0, "amber": 0}
    for it in out_items:
        for f in it["flags"]:
            counts[f["severity"]] += 1
    return {"filename": filename, "pages": pages, "split_method": method, "truncated": truncated,
            "total_items_found": len(items), "offset": offset, "next_offset": end if truncated else None,
            "items": out_items, "summary": counts,
            "disclaimer": "Prototype. Checks are against an older archive catalogue; verify on BIS "
                          "Know Your Standards."}
