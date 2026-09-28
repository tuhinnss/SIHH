"""Recommendation pipeline: expand query -> hybrid retrieve -> LLM select (enum-constrained)
-> validate -> attach clause. Degrades to retrieval-only when no LLM is available."""
import logging
import re

from app.clause import tender_clause
from app.llm import LLMClient, LLMUnavailable
from app.validator import validate_selection

log = logging.getLogger("specsure.recommender")

EXPAND_SCHEMA = {
    "type": "object",
    "properties": {
        "english_query": {"type": "string"},
        "search_terms": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["english_query", "search_terms"],
}

EXPAND_PROMPT = """You help search a catalogue of Indian Standard TITLES.
Product/spec text (may be Hindi or Hinglish): {text}

1. english_query: the text translated to plain English (unchanged if already English).
2. search_terms: up to 6 short alternative phrases that a standard's official TITLE might use for
   this product (expand abbreviations, use formal names, material and product-type synonyms).
Do NOT output any IS numbers."""

SELECT_PROMPT = """You are helping a procurement officer pick applicable Indian Standards.
Requirement: {text}

Candidate standards (the ONLY ones you may choose from; do not use any other IS number):
{candidates}

Choose up to {top_k} candidates that apply, best first.
- relevance "primary": a product/material specification the requirement should call up.
- relevance "allied": a test method, code of practice, terminology, handbook or related part.
- reason: ONE short sentence tied to the candidate's title and the requirement. Do not state facts
  (dates, certification rules) that are not in the candidate line.
- confidence: 0 to 1.
Skip candidates that do not apply."""

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def select_schema(candidate_numbers: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {"selected": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "is_number": {"type": "string", "enum": candidate_numbers},
                "relevance": {"type": "string", "enum": ["primary", "allied"]},
                "reason": {"type": "string"},
                "confidence": {"type": "number"},
            },
            "required": ["is_number", "relevance", "reason", "confidence"],
        }}},
        "required": ["selected"],
    }


class Recommender:
    def __init__(self, retriever, llm: LLMClient | None, catalogue: dict[str, dict], cert=None) -> None:
        """catalogue: display is_number -> latest-edition row (the validation table)."""
        self.retriever = retriever
        self.llm = llm
        self.catalogue = catalogue
        self.cert = cert

    def _expand(self, text: str) -> tuple[str, list[str]]:
        if not self.llm or not self.llm.providers:
            return text, []
        try:
            out = self.llm.generate_json(EXPAND_PROMPT.format(text=text), EXPAND_SCHEMA)
            eng = (out.get("english_query") or text).strip()
            terms = [t for t in out.get("search_terms", []) if isinstance(t, str)][:6]
            return eng, terms
        except (LLMUnavailable, KeyError, ValueError, TypeError):
            return text, []

    def recommend(self, text: str, top_k: int = 10, rerank: bool = False) -> dict:
        english, terms = self._expand(text)
        extra = [t for t in terms]
        if english != text:
            extra.append(text)  # embed the original-language text as well
        hits = self.retriever.search(english, top_k=top_k, rerank=rerank,
                                     extra_queries=extra or None, pool=50)
        by_num = {h["is_number"]: h for h in hits}
        llm_used, dropped = False, []
        results: list[dict] = []

        if self.llm and self.llm.providers and hits:
            cand_lines = "\n".join(
                f"- {h['is_number']} ({h['year'] or 'year unknown'}): {h['title']}" for h in hits)
            try:
                out = self.llm.generate_json(
                    SELECT_PROMPT.format(text=english, candidates=cand_lines, top_k=top_k),
                    select_schema(list(by_num)))
                valid, dropped = validate_selection(
                    out.get("selected", []), set(by_num), set(self.catalogue), query=text)
                for v in valid[:top_k]:
                    h = by_num[v["is_number"]]
                    results.append(self._card(h, v.get("relevance", "primary"),
                                              str(v.get("reason", "")).strip() or None,
                                              _clamp(v.get("confidence"))))
                llm_used = True
            except (LLMUnavailable, KeyError, ValueError, TypeError, AttributeError):
                log.warning("LLM selection failed; falling back to retrieval order")

        if not results:  # no LLM, LLM failed, or it selected nothing valid
            llm_used = False
            results = [self._card(h, "primary", None, None) for h in hits[:top_k]]
        return {"results": results, "llm_used": llm_used, "english_query": english,
                "dropped_invalid": len(dropped)}

    def _card(self, h: dict, relevance: str, reason: str | None, conf: float | None) -> dict:
        row = self.catalogue.get(h["is_number"], h)
        return {
            "is_number": row["is_number"], "title": row["title"], "year": row["year"],
            "relevance": relevance, "reason": reason,
            "confidence": conf if conf is not None else round(h["score"], 4),
            "supersedes_info": None, "allied": [],
            "certification": self.cert.for_is(row["is_number"]) if self.cert else None,
            "source_url": row["source_url"],
            "clause": tender_clause(row["is_number"], row["year"], row["title"]),
        }


def _clamp(x) -> float | None:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return None
