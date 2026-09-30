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

_RULES = """- relevance "primary": a product/material specification the requirement should call up.
- relevance "allied": a test method, code of practice, terminology, handbook or related part.
- reason: ONE short sentence tied to the candidate's title and the requirement. Do not state facts
  (dates, certification rules) that are not in the candidate line.
- confidence: 0 to 1.
Skip candidates that do not apply."""

SELECT_PROMPT = """You are helping a procurement officer pick applicable Indian Standards.
Requirement: {text}

Candidate standards (the ONLY ones you may choose from; do not use any other IS number):
{candidates}

Choose up to {top_k} candidates that apply, best first.
""" + _RULES

# Tender batches: one call expands many items, one call selects for BATCH items (not 2 calls per item).
EXPAND_MANY_PROMPT = """You help search a catalogue of Indian Standard TITLES.
Below are numbered procurement line items (English, Hindi, or Hinglish = romanised Hindi).
For EACH item return:
- item: its number.
- english_query: the item translated to plain English (unchanged if already English).
- search_terms: up to 6 short alternative phrases that a standard's official TITLE might use for
  this product (expand abbreviations, use formal names, material and product-type synonyms).
Do NOT output any IS numbers.

{items}"""

EXPAND_MANY_SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {
    "type": "object",
    "properties": {"item": {"type": "integer"}, "english_query": {"type": "string"},
                   "search_terms": {"type": "array", "items": {"type": "string"}}},
    "required": ["item", "english_query", "search_terms"]}}}, "required": ["items"]}

SELECT_MANY_PROMPT = """You are helping a procurement officer pick applicable Indian Standards for several
tender line items. For EACH numbered requirement, choose up to {top_k} of THAT requirement's own candidates
that apply, best first. A requirement's candidates are the ONLY ones you may choose for it; do not use any
other IS number. Return one entry per requirement, with its number in "item".
""" + _RULES + "\n\n{items}"

POOL = 50
BATCH = 5          # tender items per selection call
BATCH_POOL = 30    # candidates per item in a batched call (keeps the prompt small)
EXPAND_BATCH = 20  # tender items per expansion call
CACHE_SIZE = 256   # recent queries kept in memory (LRU)
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


def select_many_schema(candidate_numbers: list[str]) -> dict:
    """Batched selection. The enum is the union of all items' candidates; the validator then checks
    each item's picks against that item's own candidates."""
    single = select_schema(candidate_numbers)["properties"]["selected"]
    return {"type": "object", "properties": {"items": {"type": "array", "items": {
        "type": "object", "properties": {"item": {"type": "integer"}, "selected": single},
        "required": ["item", "selected"]}}}, "required": ["items"]}


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
        if (hit := self._cached(key)) is not None:
            return hit
        out = self._recommend(text, top_k, rerank, lang)
        self._store(key, out)
        return out

    def _cached(self, key: tuple) -> dict | None:
        with self._cache_lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return copy.deepcopy(self._cache[key])
        return None

    def _store(self, key: tuple, out: dict) -> None:
        if out["llm_used"] or not self._has_llm():
            with self._cache_lock:
                self._cache[key] = copy.deepcopy(out)
                if len(self._cache) > CACHE_SIZE:
                    self._cache.popitem(last=False)

    def _has_llm(self) -> bool:
        return bool(self.llm and self.llm.providers)

    def _candidates(self, text: str, english: str, terms: list[str], n: int, rerank: bool,
                    pool: int) -> list[dict]:
        extra = list(terms)
        if english != text:
            extra.append(text)  # embed the original-language text as well
        hits = self.retriever.search(english, top_k=n, rerank=rerank, extra_queries=extra or None, pool=pool)
        return self._with_cited(text, hits)

    def _cards(self, selected: list, hits: list[dict], text: str, english: str,
               top_k: int) -> tuple[list[dict], list[dict]]:
        """Validate the LLM's picks against THIS requirement's candidates, ground reasons -> cards."""
        by_num = {h["is_number"]: h for h in hits}
        valid, dropped = validate_selection(selected, set(by_num), set(self.catalogue), query=text)
        cards = []
        for v in valid[:top_k]:
            h = by_num[v["is_number"]]
            reason = ground_reason(str(v.get("reason") or "").strip(), _line(h), f"{text} {english}")
            cards.append(self._card(h, v.get("relevance", "primary"), reason, _clamp(v.get("confidence"))))
        return cards, dropped

    def _result(self, cards: list[dict], hits: list[dict], top_k: int, english: str, lang: str,
                dropped: list) -> dict:
        llm_used = bool(cards)
        if not cards:  # no LLM, LLM failed, or it selected nothing valid
            cards = [self._card(h, "primary", None, None) for h in hits[:top_k]]
        return {"results": cards, "llm_used": llm_used, "english_query": english, "lang": lang,
                "dropped_invalid": len(dropped)}

    def _recommend(self, text: str, top_k: int, rerank: bool, lang: str | None) -> dict:
        lang = lang or detect_lang(text)
        english, terms = self._expand(text, lang)
        use_llm = self._has_llm()
        # the LLM chooses from the whole retrieval pool; retrieval-only mode shows the top_k
        hits = self._candidates(text, english, terms, POOL if use_llm else top_k, rerank, POOL)
        cards, dropped = [], []
        if use_llm and hits:
            cand_lines = "\n".join(f"- {_line(h)}" for h in hits)
            try:
                out = self.llm.generate_json(
                    SELECT_PROMPT.format(text=english, candidates=cand_lines, top_k=top_k),
                    select_schema(list(dict.fromkeys(h["is_number"] for h in hits))))
                cards, dropped = self._cards(out.get("selected", []), hits, text, english, top_k)
            except (LLMUnavailable, KeyError, ValueError, TypeError, AttributeError):
                log.warning("LLM selection failed; falling back to retrieval order")
        return self._result(cards, hits, top_k, english, lang, dropped)

    def recommend_many(self, texts: list[str], top_k: int = 5) -> list[dict]:
        """Recommend for many tender items with few LLM calls: one expansion call per EXPAND_BATCH
        items and one selection call per BATCH items, instead of two calls per item. Validation,
        grounding, caching and the retrieval-only fallback are the same as recommend()."""
        out: list[dict | None] = [None] * len(texts)
        todo = []
        for i, t in enumerate(texts):
            if (hit := self._cached((t.strip(), top_k, False, None))) is not None:
                out[i] = hit
            else:
                todo.append(i)
        if not self._has_llm():
            for i in todo:
                out[i] = self.recommend(texts[i], top_k)
            return out
        langs = {i: detect_lang(texts[i]) for i in todo}
        exp = self._expand_many(todo, texts, langs)
        hits = {i: self._candidates(texts[i], *exp[i], BATCH_POOL, False, BATCH_POOL) for i in todo}
        for chunk in _chunks(todo, BATCH):
            listing = "\n\n".join(
                f"Requirement {n}: {exp[i][0]}\nCandidates for requirement {n}:\n"
                + "\n".join(f"- {_line(h)}" for h in hits[i]) for n, i in enumerate(chunk, 1))
            union = sorted({h["is_number"] for i in chunk for h in hits[i]})
            picks: dict = {}
            try:
                res = self.llm.generate_json(SELECT_MANY_PROMPT.format(top_k=top_k, items=listing),
                                             select_many_schema(union))
                picks = {r.get("item"): r.get("selected", []) for r in res.get("items", []) if isinstance(r, dict)}
            except (LLMUnavailable, KeyError, ValueError, TypeError, AttributeError):
                log.warning("batched LLM selection failed for %d items; retrieval order used", len(chunk))
            for n, i in enumerate(chunk, 1):
                sel = picks.get(n)
                cards, dropped = self._cards(sel if isinstance(sel, list) else [], hits[i], texts[i],
                                             exp[i][0], top_k)
                out[i] = self._result(cards, hits[i], top_k, exp[i][0], langs[i], dropped)
                self._store((texts[i].strip(), top_k, False, None), out[i])
        return out

    def _expand_many(self, todo: list[int], texts: list[str],
                     langs: dict[int, str]) -> dict[int, tuple[str, list[str]]]:
        exp = {i: (texts[i], []) for i in todo}
        for chunk in _chunks(todo, EXPAND_BATCH):
            listing = "\n".join(f"{n}. ({langs[i]}) {texts[i]}" for n, i in enumerate(chunk, 1))
            try:
                res = self.llm.generate_json(EXPAND_MANY_PROMPT.format(items=listing), EXPAND_MANY_SCHEMA)
                for r in res.get("items", []):
                    n = r.get("item") if isinstance(r, dict) else None
                    if isinstance(n, int) and 1 <= n <= len(chunk):
                        i = chunk[n - 1]
                        eng = r.get("english_query")
                        terms = [t for t in r.get("search_terms", []) if isinstance(t, str)][:6]
                        exp[i] = ((eng.strip() if isinstance(eng, str) and eng.strip() else texts[i]), terms)
            except (LLMUnavailable, KeyError, ValueError, TypeError, AttributeError):
                log.warning("batched LLM expansion failed for %d items; original text used", len(chunk))
        return exp

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


def _chunks(items: list, n: int) -> list[list]:
    return [items[i:i + n] for i in range(0, len(items), n)]


def _line(h: dict) -> str:
    """How a candidate is shown to the LLM; also the evidence its reason is grounded against."""
    return f"{h['is_number']} ({h['year'] or 'year unknown'}): {h['title']}"


def _clamp(x) -> float | None:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return None
