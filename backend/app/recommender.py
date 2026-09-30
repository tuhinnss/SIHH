"""Recommendation pipeline: expand query -> hybrid retrieve -> LLM select (enum-constrained)
-> validate -> attach clause. Degrades to retrieval-only when no LLM is available."""
import copy
import logging
import re
import threading
from collections import OrderedDict

from app.citations import extract_citations
from app.clause import tender_clause
from app.lang import detect_lang
from app.llm import LLMClient, LLMUnavailable
from app.validator import ground_reason, validate_selection

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
Product/spec text (detected language: {lang}; Hindi, Hinglish = romanised Hindi, or English): {text}

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

POOL = 50
CACHE_SIZE = 256  # recent queries kept in memory (LRU)
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
    def __init__(self, retriever, llm: LLMClient | None, catalogue: dict[str, dict], cert=None,
                 graph=None) -> None:
        """catalogue: display is_number -> latest-edition row (the validation table)."""
        self.retriever = retriever
        self.llm = llm
        self.catalogue = catalogue
        self.cert = cert
        self.graph = graph
        self._cache: OrderedDict[tuple, dict] = OrderedDict()
        self._cache_lock = threading.Lock()

    def _expand(self, text: str, lang: str = "en") -> tuple[str, list[str]]:
        if not self.llm or not self.llm.providers:
            return text, []
        try:
            out = self.llm.generate_json(EXPAND_PROMPT.format(text=text, lang=lang), EXPAND_SCHEMA)
            eng = (out.get("english_query") or text).strip()
            terms = [t for t in out.get("search_terms", []) if isinstance(t, str)][:6]
            return eng, terms
        except (LLMUnavailable, KeyError, ValueError, TypeError):
            return text, []

    def recommend(self, text: str, top_k: int = 10, rerank: bool = False, lang: str | None = None) -> dict:
        """Cached: a repeated query costs no LLM calls. A retrieval-only fallback is not cached while an
        LLM is configured (the provider may be back on the next try)."""
        key = (text.strip(), top_k, rerank, lang)
        with self._cache_lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return copy.deepcopy(self._cache[key])
        out = self._recommend(text, top_k, rerank, lang)
        if out["llm_used"] or not (self.llm and self.llm.providers):
            with self._cache_lock:
                self._cache[key] = copy.deepcopy(out)
                if len(self._cache) > CACHE_SIZE:
                    self._cache.popitem(last=False)
        return out

    def _recommend(self, text: str, top_k: int, rerank: bool, lang: str | None) -> dict:
        lang = lang or detect_lang(text)
        english, terms = self._expand(text, lang)
        extra = [t for t in terms]
        if english != text:
            extra.append(text)  # embed the original-language text as well
        use_llm = bool(self.llm and self.llm.providers)
        # the LLM chooses from the whole retrieval pool; retrieval-only mode shows the top_k
        hits = self.retriever.search(english, top_k=POOL if use_llm else top_k, rerank=rerank,
                                     extra_queries=extra or None, pool=POOL)
        hits = self._with_cited(text, hits)
        by_num = {h["is_number"]: h for h in hits}
        llm_used, dropped = False, []
        results: list[dict] = []

        if use_llm and hits:
            cand_lines = "\n".join(f"- {_line(h)}" for h in hits)
            try:
                out = self.llm.generate_json(
                    SELECT_PROMPT.format(text=english, candidates=cand_lines, top_k=top_k),
                    select_schema(list(by_num)))
                valid, dropped = validate_selection(
                    out.get("selected", []), set(by_num), set(self.catalogue), query=text)
                for v in valid[:top_k]:
                    h = by_num[v["is_number"]]
                    reason = ground_reason(str(v.get("reason") or "").strip(), _line(h), f"{text} {english}")
                    results.append(self._card(h, v.get("relevance", "primary"), reason,
                                              _clamp(v.get("confidence"))))
                llm_used = True
            except (LLMUnavailable, KeyError, ValueError, TypeError, AttributeError):
                log.warning("LLM selection failed; falling back to retrieval order")

        if not results:  # no LLM, LLM failed, or it selected nothing valid
            llm_used = False
            results = [self._card(h, "primary", None, None) for h in hits[:top_k]]
        return {"results": results, "llm_used": llm_used, "english_query": english, "lang": lang,
                "dropped_invalid": len(dropped)}

    def _with_cited(self, text: str, hits: list[dict]) -> list[dict]:
        """Standards named in the requirement text itself (matched against the catalogue) join the
        candidate list, at the front."""
        if not self.graph:
            return hits
        have = {h["is_number"] for h in hits}
        extra = []
        for c in extract_citations(text):
            e = self.graph.cat.resolve(c)
            if e and e.is_number not in have and e.is_number in self.catalogue:
                extra.append(dict(self.catalogue[e.is_number], score=1.0))
                have.add(e.is_number)
        return extra + hits

    def _card(self, h: dict, relevance: str, reason: str | None, conf: float | None) -> dict:
        row = self.catalogue.get(h["is_number"], h)
        return {
            "is_number": row["is_number"], "title": row["title"], "year": row["year"],
            "relevance": relevance, "reason": reason,
            "confidence": conf if conf is not None else round(h["score"], 4),
            "key": row.get("key"),
            "supersedes_info": self.graph.supersedes_info(row["key"]) if self.graph and row.get("key") else None,
            "allied": self.graph.allied(row["key"], limit=8) if self.graph and row.get("key") else [],
            "editions": sorted(self.graph.cat.entries[row["key"]].years)
            if self.graph and row.get("key") in self.graph.cat.entries else None,
            "certification": self.cert.for_is(row["is_number"]) if self.cert else None,
            "source_url": row["source_url"],
            "clause": tender_clause(row["is_number"], row["year"], row["title"]),
        }


def _line(h: dict) -> str:
    """How a candidate is shown to the LLM; also the evidence its reason is grounded against."""
    return f"{h['is_number']} ({h['year'] or 'year unknown'}): {h['title']}"


def _clamp(x) -> float | None:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return None
