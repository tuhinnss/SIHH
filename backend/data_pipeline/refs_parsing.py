"""Pure text parsing for extract_refs: scope snippet, referred-standards lists, supersession.

Real OCR quirks handled (seen in archive.org *_djvu.txt):
 * The reference list is usually an Annex ("LIST OF REFERRED INDIAN STANDARDS") laid out in
   columns, so numbers appear as bare lines ("4905 : 2015/ ISO 24153 : 2009", "12235" followed by
   "(Part 1) : 2004" lines) with titles in a separate block.
 * Page numbers appear as lone 2-3 digit lines; year-only lines ("2004") wrap from part lines.
 * Older standards list references inline under a "REFERENCES" clause with "IS 1234 : 1980".
"""
import re

from app.citations import Citation, extract_citations

SCOPE_CHARS = 800
_SCOPE_HEAD = re.compile(r"^\s*(?:\d+\.?\s+)?SCOPE\s*$", re.I | re.M)
_REFS_HEAD = re.compile(r"^\s*(?:\d+\.?\s+)?(?:NORMATIVE\s+)?REFERENCES?\s*$", re.I | re.M)
_ANNEX_LIST = re.compile(r"LIST\s+OF\s+(?:REFERRED|REFERENCED)[^\n]*", re.I)
_ISNO = re.compile(r"^\s*IS\s*No\.?\s*$", re.I)
_NEXT_ANNEX = re.compile(r"^\s*ANNEX\s+[B-Z]\b", re.M)
_NEXT_CLAUSE = re.compile(r"^\s*\d+\.?\s+[A-Z][A-Z ,&-]{3,}\s*$", re.M)
_BARE = re.compile(r"^\s*(?P<num>\d{2,6})\s*(?:[:;]\s*(?P<year>(?:19|20)\d{2}))?\s*(?:/.*)?$")
# inline table row under a REFERENCES clause: "1239:2004 Steel tubes ...", "12235 (Part 1) ; 2004 Title"
_ROW = re.compile(
    r"^\s*(?P<num>\d{2,6})\s*(?:\(\s*(?:Part|Pt)\.?\s*(?P<part>\d+[A-Za-z]?)(?:\s*[/,]\s*Sec(?:tion)?\.?\s*(?P<sec>\d+))?\s*\))?"
    r"\s*[:;]\s*(?P<year>(?:19|20)\d{2})(?!\d)", re.M)
_PARTLINE = re.compile(
    r"^\s*\(\s*(?:Part|Pt)\.?\s*(?P<part>\d+[A-Za-z]?)(?:\s*[/,]\s*Sec(?:tion)?\.?\s*(?P<sec>\d+))?\s*\)"
    r"\s*:?\s*(?P<year>(?:19|20)\d{2})?\s*$", re.I)


def _ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


_NEXT_HEAD_FLAT = re.compile(r"\s\d{1,2}\.?\s+[A-Z]{4,}(?:\s+[A-Z&,-]{2,})*\s+(?=[A-Z][a-z]|\d|\()")


def trim_scope(snippet: str) -> str:
    """Cut a flattened scope snippet at the start of the next numbered clause ("2 REFERENCES The ...")."""
    m = _NEXT_HEAD_FLAT.search(snippet)
    return snippet[: m.start()].strip() if m else snippet


def find_scope(text: str) -> str | None:
    """First ~800 chars after the SCOPE heading (whitespace normalised)."""
    for m in _SCOPE_HEAD.finditer(text):
        nxt = next((l for l in text[m.end(): m.end() + 200].splitlines() if l.strip()), "")
        if _NEXT_CLAUSE.match(nxt) or re.match(r"^\s*(?:\d+\.?\s+)?[A-Z][A-Z ,&-]{3,}\s*$", nxt):
            continue  # table-of-contents entry: next line is another heading
        snippet = trim_scope(_ws(text[m.end(): m.end() + SCOPE_CHARS * 2])[:SCOPE_CHARS])
        if len(snippet) > 60:  # skip table-of-contents hits
            return snippet
    return None


def _cite_key(number: str, part: str | None = None, section: str | None = None) -> str:
    key = f"IS-{number}"
    if part:
        key += f"-P{part}"
    if section:
        key += f"-S{section}"
    return key.upper()


def parse_bare_list(region: str) -> list[dict]:
    """Column-style reference list -> [{key, number, part, section, year}]."""
    out, pending, seen_hdr = [], None, False
    for line in region.splitlines():
        if _ISNO.match(line):
            seen_hdr = True
            continue
        if not seen_hdr:
            continue
        pm = _PARTLINE.match(line)
        if pm and pending:
            out.append({"number": pending, "part": pm["part"], "section": pm["sec"],
                        "year": int(pm["year"]) if pm["year"] else None})
            continue
        bm = _BARE.match(line)
        if not bm:
            continue
        num, year = bm["num"], bm["year"]
        if year:
            out.append({"number": num, "part": None, "section": None, "year": int(year)})
            pending = None
        elif len(num) >= 4 and not (1900 <= int(num) <= 2099):
            pending = num          # e.g. "12235" awaiting "(Part n)" lines; ignores page numbers/years
    for r in out:
        r["key"] = _cite_key(r["number"], r["part"], r["section"])
    return out


def _region_after(text: str, start: int, span: int, stop: re.Pattern) -> str:
    seg = text[start: start + span]
    m = stop.search(seg, 20)
    return seg[: m.start()] if m else seg


def find_refs(text: str) -> list[dict]:
    """Referred standards from the Annex list and/or the REFERENCES clause (deduped by key)."""
    refs: dict[str, dict] = {}

    def add(items):
        for it in items:
            refs.setdefault(it["key"], it)

    for m in _ANNEX_LIST.finditer(text):
        region = text[max(0, m.start() - 2500): m.start()] + _region_after(text, m.start(), 9000, _NEXT_ANNEX)
        add(parse_bare_list(region))
        add(_cites(region))
    for m in _REFS_HEAD.finditer(text):
        region = _region_after(text, m.end(), 3500, _NEXT_CLAUSE)
        add(parse_inline_rows(region))
        add(_cites(region))
    return list(refs.values())


def parse_inline_rows(region: str) -> list[dict]:
    out = []
    for m in _ROW.finditer(region):
        out.append({"key": _cite_key(m["num"], m["part"], m["sec"]), "number": m["num"],
                    "part": m["part"], "section": m["sec"], "year": int(m["year"])})
    return out


def _cites(region: str) -> list[dict]:
    return [_cdict(c) for c in extract_citations(region)]


def _cdict(c: Citation) -> dict:
    return {"key": c.key, "number": c.number, "part": c.part, "section": c.section, "year": c.year}


def scope_refs(scope: str | None) -> list[dict]:
    return _cites(scope) if scope else []


_SUPERSEDE = re.compile(r"supersed(?:e|es|ed|ing)", re.I)
_BARE_MORE = re.compile(r"(?:,|&|\band\b)\s*(\d{2,6})(?!\d)(?:\s*[:\-]\s*(?:19|20)\d{2})?")


def find_supersedes(text: str) -> list[dict]:
    """IS numbers named next to 'supersede*' in running text or titles ("(Superseding IS 1502, 2135)")."""
    out: dict[str, dict] = {}
    for m in _SUPERSEDE.finditer(text):
        if re.search(r"\b(?:not|never|no)\s+(?:\w+\s+){0,2}$", text[max(0, m.start() - 30): m.start()], re.I):
            continue  # "does not supersede IS ..."
        window = text[m.end(): m.end() + 160]
        window = re.split(r"[.;\]\)]\s|\n\n", window, maxsplit=1)[0] if "(" not in window[:3] else window
        cites = extract_citations(window)
        for c in cites:
            out.setdefault(c.key, _cdict(c))
        if cites:  # bare follow-on numbers: "IS 1502, 2135"
            tail = window[window.find(cites[-1].raw) + len(cites[-1].raw):]
            for n in _BARE_MORE.findall(tail):
                out.setdefault(_cite_key(n), {"key": _cite_key(n), "number": n, "part": None,
                                              "section": None, "year": None})
    return list(out.values())
