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


def extract_text(pdf_bytes: bytes) -> tuple[str, int, int]:
    """-> (text, pages, image_only_pages). Image-only pages (scans) have no text layer and OCR is
    not included, so their line items are invisible to the splitter."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    pages, image_only = [], 0
    for p in doc:
        t = p.get_text("text")
        if not t.strip() and p.get_images():
            image_only += 1
        pages.append(t)
    return "\n".join(pages)[:MAX_CHARS], len(pages), image_only


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
