"""Draft certification rows from BIS "Products under Compulsory Certification - Scheme I (ISI Mark)".

Input: that bis.gov.in page saved as PDF (browser "Save as PDF" keeps the links). For every linked
order PDF (Quality Control Orders, amendments, extension orders) it records which IS numbers the order
names and every sentence saying when something comes into force. Output is a DRAFT for the user:
data/raw/certification_draft.csv with a suggested start date AND the sentences it came from. Nothing
here writes data/certification.csv - the user confirms each row and copies it there by hand.

Order PDFs are cached in data/raw/bis_orders/ (git-ignored); 1 request/second; files over 5 MB (mostly
scanned gazettes or booklets) are skipped and listed for checking by hand.
Usage: python -m data_pipeline.qco_orders "<saved page>.pdf"
"""
import calendar
import csv
import hashlib
import re
import sys
import time
from datetime import date, timedelta

import pymupdf
import requests

from app.citations import _CITE, extract_citations
from data_pipeline.common import RAW

ORDERS = RAW / "bis_orders"
OUT = RAW / "certification_draft.csv"
PAGE_URL = "https://www.bis.gov.in/product-certification/products-under-compulsory-certification/scheme-i-mark-scheme/"
MAX_BYTES = 5_000_000
UA = {"User-Agent": "SpecSure-SIH26108-prototype"}

_SERIAL = re.compile(r"^\d*\.$")  # the printed page truncates serial numbers ("0.", "1.", ".")
_IS_HEAD = re.compile(r"^IS\b")
_IS_CONT = re.compile(r"^(?:[\d(][\w():\s/-]*|Part\b.*|Sec\w*\b.*)$")  # "1:1982", "1)", "Part 2", "2015"
_FORCE = re.compile(r"[^.;]*(?:come\s+into\s+(?:force|effect)|with\s+effect\s+from|date\s+of\s+implementation"
                    r"|date\s+of\s+enforcement)[^.;]*", re.I | re.S)
_MONTHS = "january february march april may june july august september october november december".split()
_DATE_WORDS = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?(" + "|".join(_MONTHS) + r"),?\s+((?:19|20)\d{2})", re.I)
_DATE_NUM = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-]((?:19|20)\d{2})\b")


def norm_is(head: str) -> str:
    """'IS 432 : Part 1:1982' -> 'IS 432 (Part 1):1982' so the citation parser reads the part. Already
    bracketed forms ('IS 1489 (Part 1)', 'IS 302 (Part 2/Sec 3)') are left alone."""
    s = re.sub(r"\s+", " ", head).strip()
    if not re.search(r"\(\s*Part", s, re.I):
        s = re.sub(r"[:\s]*\bPart\s*(\w+)\s*\)?", r" (Part \1)", s, flags=re.I)
    if not re.search(r"[(/]\s*Sec", s, re.I):
        s = re.sub(r"[:\s]*\(?\s*\bSec(?:tion)?\.?\s*(\w+)\s*\)?", r" (Sec \1)", s, flags=re.I)
    return s


def parse_rows(text: str) -> list[dict]:
    """Product rows of the saved page: serial line, IS number (may wrap), product name (until a blank)."""
    lines = [l.strip() for l in text.splitlines()]
    rows = []
    for i, line in enumerate(lines):
        if not (_SERIAL.match(line) and i + 1 < len(lines) and _IS_HEAD.match(lines[i + 1])):
            continue
        head, j = [lines[i + 1]], i + 2
        while j < len(lines) and lines[j] and _IS_CONT.match(lines[j]) and len(lines[j]) < 20:
            head.append(lines[j])
            j += 1
        prod = []
        while j < len(lines) and lines[j] and not _SERIAL.match(lines[j]):
            prod.append(lines[j])
            j += 1
        h = " ".join(head)
        if prod and h.count("(") > h.count(")") and (m := re.match(r"^([\d\s&,]+\))\s*(.*)$", prod[0])):
            h, prod[0] = f"{h} {m.group(1)}", m.group(2)  # "IS 15111 (Part" / "1 & 2) Self Ballasted ..."
        h = norm_is(h)
        product = re.sub(r"^[:\s]*(?:19|20)\d{2}\s*", "", re.sub(r"\s+", " ", " ".join(prod)).strip(" ."))  # wrapped year
        if both := re.match(r"^(.*?)\(\s*Part\s*(\w+)\s*&\s*(\w+)\s*\)", h, re.I):  # one row, two parts
            heads = [f"{both.group(1)}(Part {both.group(2)})", f"{both.group(1)}(Part {both.group(3)})"]
        else:
            heads = [h]
        for hh in heads:
            cites = extract_citations(hh)
            if cites:
                rows.append({"key": cites[0].key, "is_raw": hh.strip(), "product": product})
    return rows


def force_sentences(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", m.group(0)).strip() for m in _FORCE.finditer(text)]


# Schedule tables give the start per product: "IS 1148: 2009 Steel Rivet Bars ... 9 months from date of publication"
_TERM = re.compile(r"with\s+immediate\s+effect|(\d+)\s*(months?|days?)\s+from\s+(?:the\s+)?date\s+of\s+(?:its\s+)?"
                   r"publication|(?:w\.?e\.?f\.?|with\s+effect\s+from)\s+[^;]{0,40}", re.I)


def schedule_terms(text: str) -> dict[str, str]:
    """IS key -> the start term written after it in the order's schedule table (up to the next IS number)."""
    flat = re.sub(r"\s+", " ", text)
    ms = list(_CITE.finditer(flat))
    out: dict[str, str] = {}
    for i, m in enumerate(ms):
        seg = flat[m.end(): ms[i + 1].start() if i + 1 < len(ms) else m.end() + 400][:400]
        t = _TERM.search(seg)
        cites = extract_citations(m.group(0))
        if t and cites:
            out.setdefault(cites[0].key, t.group(0).strip())
    return out


_MASTHEAD = re.compile(r"NEW DELHI,\s*[A-Z]+DAY,\s*(" + "|".join(_MONTHS) + r")\s+(\d{1,2}),\s*((?:19|20)\d{2})", re.I)
_SIGNED = re.compile(r"New Delhi,\s*the\s+([^.;]{6,30}?(?:19|20)\d{2})", re.I)


def publication_date(text: str) -> date | None:
    """Date of publication in the Gazette: the English masthead 'NEW DELHI, WEDNESDAY, FEBRUARY 19, 2020'
    (orders are bilingual, Hindi first), else the order's own 'New Delhi, the 14th February, 2020'. No
    other date is guessed: the text also cites older orders' dates."""
    flat = re.sub(r"\s+", " ", text)
    if m := _MASTHEAD.search(flat):
        return date(int(m.group(3)), _MONTHS.index(m.group(1).lower()) + 1, int(m.group(2)))
    if m := _SIGNED.search(flat):
        ds = dates_in(m.group(1))
        return ds[0] if ds else None
    return None


def apply_term(term: str, published: date | None) -> date | None:
    m = _TERM.fullmatch(term.strip()) or _TERM.match(term.strip())
    if not m:
        return None
    if term.lower().startswith("with immediate effect"):
        return published
    if m.group(1) and published:
        n = int(m.group(1))
        if m.group(2).lower().startswith("day"):
            return published + timedelta(days=n)
        y, mo = divmod(published.month - 1 + n, 12)
        last = calendar.monthrange(published.year + y, mo + 1)[1]
        return date(published.year + y, mo + 1, min(published.day, last))
    ds = dates_in(term)
    return ds[0] if ds else None


def dates_in(sentence: str) -> list[date]:
    out = []
    for d, mon, y in _DATE_WORDS.findall(sentence):
        out.append(date(int(y), _MONTHS.index(mon.lower()) + 1, int(d)))
    for d, m, y in _DATE_NUM.findall(sentence):
        try:
            out.append(date(int(y), int(m), int(d)))
        except ValueError:
            pass
    return out


def fetch(uri: str, state: dict) -> tuple[str, str]:
    """-> (status, text). Cached on disk; polite spacing; size cap."""
    path = ORDERS / (hashlib.sha256(uri.encode()).hexdigest()[:16] + ".pdf")
    if not path.exists() and not (ORDERS / (path.name + ".skip")).exists():
        wait = 1.0 - (time.monotonic() - state.get("last", 0.0))
        if wait > 0:
            time.sleep(wait)
        state["last"] = time.monotonic()
        for attempt in range(3):
            try:
                with requests.get(uri, headers=UA, timeout=60, stream=True) as r:
                    size = int(r.headers.get("content-length") or 0)
                    if r.status_code >= 500:  # transient: retry now, and on the next run
                        raise requests.RequestException(f"HTTP {r.status_code}")
                    if r.status_code != 200 or size > MAX_BYTES:  # 404 / too big: record and move on
                        (ORDERS / (path.name + ".skip")).write_text(f"HTTP {r.status_code}, {size} bytes", encoding="utf-8")
                        break
                    data, start = bytearray(), time.monotonic()
                    for chunk in r.iter_content(65536):  # the read timeout alone lets a trickle run forever
                        data += chunk
                        if time.monotonic() - start > 180 or len(data) > MAX_BYTES:
                            raise requests.RequestException("too slow or too big")
                    path.write_bytes(bytes(data))
                    break
            except requests.RequestException:
                time.sleep(2 * 2 ** attempt)
    if not path.exists():
        skip = ORDERS / (path.name + ".skip")
        return ("skipped: " + skip.read_text(encoding="utf-8") if skip.exists() else "download failed"), ""
    try:
        text = "\n".join(p.get_text() for p in pymupdf.open(path))
    except Exception:  # noqa: BLE001 - not a readable PDF
        return "unreadable", ""
    return ("ok" if len(text.strip()) > 200 else "no text (scanned?)"), text


def main(page_pdf: str) -> None:
    ORDERS.mkdir(parents=True, exist_ok=True)
    page = pymupdf.open(page_pdf)
    rows = parse_rows("\n".join(p.get_text() for p in page))
    uris = list(dict.fromkeys(l["uri"] for p in page for l in p.get_links()
                              if l.get("uri", "").lower().split("?")[0].endswith(".pdf")))
    print(f"{len(rows)} product rows, {len(uris)} linked PDFs")
    by_key: dict[str, list[tuple[str, str]]] = {}   # IS key -> [(order url, "come into force" sentence)]
    sched: dict[str, list[tuple[str, str, date | None, date | None]]] = {}  # key -> [(url, term, published, start)]
    unread, state = [], {}
    for n, uri in enumerate(uris, 1):
        status, text = fetch(uri, state)
        if status != "ok":
            unread.append((uri, status))
        keys = {c.key for c in extract_citations(text)}
        for s in force_sentences(text):
            for k in keys:
                by_key.setdefault(k, []).append((uri, s))
        pub = publication_date(text)
        for k, term in schedule_terms(text).items():
            sched.setdefault(k, []).append((uri, term, pub, apply_term(term, pub)))
        if n % 25 == 0:
            print(f"  {n}/{len(uris)} orders read ({len(unread)} unread)")
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["product", "is_number", "scheme", "suggested_effective_date", "how", "schedule_evidence",
                    "n_orders", "force_sentences"])
        for r in rows:
            ev = list(dict.fromkeys(by_key.get(r["key"], [])))
            sc = sched.get(r["key"], [])
            starts = sorted(d for *_, d in sc if d)  # the latest start (an amendment may postpone it)
            if starts:  # latest = conservative: never treats a requirement as active before it may be
                start = starts[-1].isoformat()
                how = f"schedule term + Gazette date; latest of {len(starts)} (earliest {starts[0].isoformat()})"
            else:
                ds = sorted({d for _, s in ev for d in dates_in(s)})
                start, how = (ds[-1].isoformat(), "date in a 'come into force' sentence") if ds else ("", "")
            w.writerow([r["product"], r["is_raw"], "ISI/QCO", start, how,
                        " || ".join(f"{t} (order dated {p or '?'}) [{u}]" for u, t, p, _ in sc)[:1500],
                        len({u for u, _ in ev}), " || ".join(f"{s} [{u}]" for u, s in ev)[:3000]])
    have = sum(1 for r in rows if by_key.get(r["key"]) or sched.get(r["key"]))
    print(f"draft -> {OUT} ({have}/{len(rows)} products with order evidence)")
    print(f"{len(unread)} linked PDFs not read (check by hand if they matter):")
    for uri, status in unread:
        print(f"  {status}: {uri}")


if __name__ == "__main__":
    main(sys.argv[1])
