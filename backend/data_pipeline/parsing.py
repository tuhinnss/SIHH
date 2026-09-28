"""Parse archive.org `gov.in.is.*` items into structured catalogue rows.

The identifier is the reliable structured source:
    gov.in.is.[<family>.][<joint prefix>.]<number>[.<part>[.<section>]][.<flag>].<year>
Titles look like "IS 1783 : Part 2 : 2014: Drums, ..." (format varies), so the title
text is only used for the human-readable title and the designation (IS, IS/ISO, SP...).
The archive `date` field is an upload date, NOT the edition year; year comes from the id.
"""
import re
from dataclasses import asdict, dataclass

PREFIX = "gov.in.is."
FLAGS = {"h": "hindi", "b": "bilingual", "t": "tentative", "s": "supplement"}
FAMILIES = {"sp", "qc", "guide", "ihb"}
JOINT = {"iso", "iec", "ieee", "tr", "ts", "pas"}

_HDR = re.compile(
    r"^(?P<hdr>[^:]+?)"
    r"(?:\s*:\s*(?:(?:Part|Pt|Section|Sec)\s*[\w-]+\s*:\s*)*\d{4})?"
    r"\s*:\s+(?P<title>.+)$", re.S)
_DESIG = re.compile(r"^[A-Za-z]+(?:/[A-Za-z]+)*(?:\s+Guide)?")


_MOJI = re.compile(r"[\u00c2\u00c3\u00e2][^\x00-\x7f]+")


def _to_bytes(chunk: str) -> bytes:
    out = bytearray()
    for ch in chunk:
        try:
            out += ch.encode("cp1252")
        except UnicodeEncodeError:
            out += ch.encode("latin-1", errors="ignore")
    return bytes(out)


def _decode_prefix(chunk: str) -> str | None:
    """Decode the longest prefix of `chunk` that is valid mojibake; keep the tail as is."""
    for end in range(len(chunk), 1, -1):
        try:
            return _to_bytes(chunk[:end]).decode("utf-8") + chunk[end:]
        except UnicodeDecodeError:
            continue
    return None


def _repair_chunk(m: re.Match) -> str:
    chunk = m.group(0)
    for _ in range(3):  # some titles are double-encoded
        fixed = _decode_prefix(chunk)
        if fixed is None:
            break
        chunk = fixed
        if not _MOJI.match(chunk):
            break
    return chunk


def fix_mojibake(text: str) -> str:
    """Repair UTF-8 text mis-decoded as cp1252/latin-1 (seen in some archive titles)."""
    return _MOJI.sub(_repair_chunk, text)


@dataclass
class Standard:
    identifier: str
    key: str            # IS-{num}-P{part}-S{sec}, year ignored (joint prefix kept)
    is_number: str      # display form, e.g. "IS 1783 (Part 2)"
    designation: str
    number: str
    part: str | None
    section: str | None
    year: int | None
    title: str
    flags: list[str]
    source_url: str
    ia_date: str | None


def parse_item(doc: dict) -> Standard | None:
    ident = doc["identifier"]
    if not ident.startswith(PREFIX):
        return None
    toks = ident[len(PREFIX):].split(".")
    year = int(toks.pop()) if toks and re.fullmatch(r"\d{4}", toks[-1]) else None

    family = None
    joint: list[str] = []
    if toks and toks[0] in FAMILIES:
        family = toks.pop(0)
    while toks and toks[0] in JOINT:
        joint.append(toks.pop(0))

    flags: list[str] = []
    rest: list[str] = []
    for i, t in enumerate(toks):
        if t in FLAGS and i > 0:
            flags.append(FLAGS[t])
        elif t == "od" and i > 0:
            rest.append("OD" + (toks[i + 1] if i + 1 < len(toks) else ""))
            toks[i + 1:i + 2] = []
        else:
            rest.append(t)
    number = rest[0] if rest else ""
    part = rest[1] if len(rest) > 1 else None
    section = rest[2] if len(rest) > 2 else None

    raw_title = fix_mojibake((doc.get("title") or "").strip())
    m = _HDR.match(raw_title)
    hdr, title = (m["hdr"], m["title"].strip()) if m else ("", raw_title)
    d = _DESIG.match(hdr.strip())
    designation = d.group(0) if d else ("IS" if not family else family.upper())

    label = f"{designation} {number}".strip()
    if part:
        label += f" (Part {part})"
    if section:
        label += f" (Sec {section})"
    key = "-".join(x.upper() for x in [family or "is", *joint] if x) + f"-{number}"
    if part:
        key += f"-P{part}"
    if section:
        key += f"-S{section}"
    if "supplement" in flags:
        key += "-SUPP"
    return Standard(
        identifier=ident, key=key.upper(), is_number=label, designation=designation,
        number=number, part=part, section=section, year=year, title=title, flags=flags,
        source_url=f"https://archive.org/details/{ident}", ia_date=doc.get("date"))


def to_dict(s: Standard) -> dict:
    return asdict(s)
