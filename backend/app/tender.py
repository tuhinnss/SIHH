"""Tender PDF -> text -> line items. Heuristics first (numbered lines, BOQ rows, bullets);
the LLM only helps split when heuristics find too little."""
import re

import pymupdf  # PyMuPDF

MAX_CHARS = 60000
_START = re.compile(r"^\s*(?:item\s*(?:no\.?)?\s*)?(?P<n>\d{1,3}(?:\.\d{1,2}){0,2})\s*[.)\]:-]?\s+(?P<t>\S.*)$", re.I)
_LONE_NO = re.compile(r"^\s*\d{1,3}[.)]?\s*$")
_BULLET = re.compile(r"^\s*[•●▪◦\-–*]\s+(?P<t>\S.*)$")
_NOISE = re.compile(r"^\s*(page\s*\d+(\s*of\s*\d+)?|\d+\s*/\s*\d+)\s*$", re.I)
_QTYUNIT = re.compile(r"^\s*(?:\d+(?:[.,]\d+)?\s*)?(nos?\.?|pcs?|set|sets|mtr|m|kg|ltr|lot|unit|units|each|sqm|rmt)\s*$", re.I)


def extract_text(pdf_bytes: bytes, max_chars: int | None = MAX_CHARS) -> tuple[str, int, int]:
    """-> (text, pages, image_only_pages). Image-only pages (scans) have no text layer and OCR is
    not included, so their line items are invisible to the splitter. max_chars=None: no cap."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    pages, image_only = [], 0
    for p in doc:
        t = p.get_text("text")
        if not t.strip() and p.get_images():
            image_only += 1
        pages.append(t)
    return "\n".join(pages)[:max_chars], len(pages), image_only


# GeM "Bid Document" PDFs: each item is a heading followed by a "Technical Specifications" marker and a
# section that ends at "Consignees/Reporting Officer". Everything else is forms, T&Cs and GeM's own
# "GeMARPTS" search suggestions (other catalogue categories with THEIR standards, not the buyer's).
# Two layouts: BOQ bids ("<hindi> /Technical Specifications", specs in attached files) and category bids
# ("Technical Specifications/<hindi>", a parameter table; the heading can wrap and ends "( 40 pieces )").
# The Hindi labels extract garbled, so only the English markers are used.
_GEM_ID = re.compile(r"GEM/\d{4}/B/\d+")
_GEM_SPEC = re.compile(r"(?:^|/)\s*Technical Specifications\s*(?:/|$)", re.I)
_GEM_END = re.compile(r"Consignees/Reporting Officer", re.I)
_GEM_BOILER = re.compile(  # link-table cells come out as separate lines ("Specification Document", "View File")
    r"^(?:Specification Document|BOQ Detail Document|View File)(?:\s+View File)?$|^Advisory-Please refer"
    r"|^Specification$|^Specification Name|^Bid Requirement|^Values\)|As per GeM Category", re.I)
# Fields between heading and marker: the Make-in-India note ("(... Minimum 50% and 20% Local" / "Content
# required ... Local Supplier respectively)"), "Bis Required" / "Yes".
_GEM_NOTE = re.compile(r"Local\s*$|Local Supplier|^Content required|Minimum \d+% and \d+%|^respectively"
                       r"|^Bis Required$|^(?:Yes|No)$", re.I)
SPEC_CHARS = 600  # category-bid parameter tables are long; the heading carries most of the meaning


def _open(line: str) -> bool:
    """A heading line that continues on the next line: unbalanced '(' or a trailing '/', ',' or '-'."""
    return line.count("(") > line.count(")") or line.endswith(("/", ",", "-"))


def gem_items(text: str) -> list[str]:
    """Line items of a GeM bid document ([] if the text is not one): the item heading plus any
    specification text listed under it."""
    if not _GEM_ID.search(text):
        return []
    lines = [l.strip() for l in text.splitlines() if l.strip() and not _NOISE.match(l)]
    items = []
    for i, line in enumerate(lines):
        if not _GEM_SPEC.search(line) or i == 0:
            continue
        spec = []
        for nxt in lines[i + 1:]:
            if _GEM_END.search(nxt) or _GEM_SPEC.search(nxt):
                break
            if not _GEM_BOILER.search(nxt):
                spec.append(nxt)
        h = i - 1
        while h > 0 and _GEM_NOTE.search(lines[h]):
            h -= 1
        head = [lines[h]]
        while h > 0 and _open(lines[h - 1]):  # wrapped heading
            h -= 1
            head.insert(0, lines[h])
        heading = re.sub(r"\(\s*\d+\s*pieces?\s*\)|\(V\d+\)", "", " ".join(head), flags=re.I)
        spec_text = re.sub(r"\s+", " ", " ".join(spec)).strip()[:SPEC_CHARS]
        items.append(re.sub(r"\s+", " ", f"{heading} {spec_text}").strip())
    return items


def split_items(text: str) -> list[str]:
    items: list[list[str]] = []
    lines = [l.rstrip() for l in text.splitlines() if l.strip() and not _NOISE.match(l)]
    i = 0
    while i < len(lines):
        line = lines[i]
        m, b = _START.match(line), _BULLET.match(line)
        if _LONE_NO.match(line) and i + 1 < len(lines):  # BOQ table: serial no. on its own line
            items.append([lines[i + 1].strip()])
            i += 2
            continue
        if m and not _QTYUNIT.match(m["t"]):
            items.append([m["t"].strip()])
        elif b:
            items.append([b["t"].strip()])
        elif items:
            items[-1].append(line.strip())
        i += 1
    out = []
    for it in items:
        s = " ".join(it)
        s = re.sub(r"\s+", " ", s).strip()
        if len(s) >= 15 and not _QTYUNIT.match(s):
            out.append(s)
    return out


LLM_SPLIT_SCHEMA = {"type": "object", "properties": {
    "items": {"type": "array", "items": {"type": "string"}}}, "required": ["items"]}


def llm_split(text: str, llm) -> list[str]:
    """Ask the LLM to copy out each procurement line item verbatim (no rewriting)."""
    prompt = ("Below is text extracted from a procurement tender. List every distinct product / "
              "material / equipment line item requirement, each as ONE string copied verbatim "
              "from the text (with its specification details). Skip terms and conditions.\n\n"
              + text[:12000])
    out = llm.generate_json(prompt, LLM_SPLIT_SCHEMA)
    return [s.strip() for s in out.get("items", []) if isinstance(s, str) and len(s.strip()) >= 15]


def paragraph_split(text: str) -> list[str]:
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    return [p for p in paras if len(p) >= 25]
