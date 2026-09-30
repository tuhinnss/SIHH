"""Find IS citations in free text and normalise them to catalogue keys (year ignored).

Handles e.g. "IS 1554 (Part 1) : 1988", "IS/IEC 60947-2 : 2016", "IS 1239 (Pt 1)",
"IS:456-2000", "IS 12970 (Part 3/Sec 2)". Keys follow data_pipeline.parsing:
IS-[JOINT-]{num}[-P{part}][-S{sec}].
"""
import re
from dataclasses import dataclass

_JOINT = r"(?:ISO|IEC|IEEE|TR|TS|PAS)"
# Real tenders also write parts as "(Part-I)", "(Pt II)" or a bare "part III" after the year.
_PART = r"(?i:Part|Pt)\.?\s*[-:]?\s*"
_PNUM = r"[A-Za-z]?\d+[A-Za-z]?|(?i:[IVX]{1,4})\b"
_CITE = re.compile(
    rf"""(?<![A-Za-z])IS(?P<joint>(?:\s*/\s*{_JOINT})*)\s*[:\-]?\s*(?P<num>\d{{1,6}})
        (?:\s*\(\s*{_PART}(?P<p1>{_PNUM})\s*(?:[/,\-]\s*(?:Sec(?:tion)?\.?\s*)?(?P<s1>\d+))?\s*\))?
        (?:\s*\(\s*(?:Sec(?:tion)?\.?)\s*(?P<s2>\d+)\s*\))?
        (?P<hy>(?:\s*-\s*[A-Za-z]?\d{{1,3}}[A-Za-z]?(?!\d))*)
        (?:\s*[:\-/]\s*(?P<year>(?:19|20)\d{{2}})(?!\d))?
        (?:\s*[,:/\-]?\s*{_PART}(?P<p3>\d+\b|(?i:[IVX]{{1,4}})\b)(?:\s*[:\-/]?\s*(?P<year2>(?:19|20)\d{{2}})(?!\d))?)?""",
    re.X)
_ROMAN = {"I": "1", "II": "2", "III": "3", "IV": "4", "V": "5", "VI": "6", "VII": "7", "VIII": "8", "IX": "9", "X": "10"}


def _arabic(part: str | None) -> str | None:
    return _ROMAN.get(part.upper(), part) if part else part


@dataclass(frozen=True)
class Citation:
    raw: str
    key: str
    number: str
    part: str | None
    section: str | None
    year: int | None
    joint: tuple[str, ...]


_LEAD = (r"(?:as\s+per|conform(?:s|ing)?\s+to|confirming\s+to|according\s+to|compl(?:ying|iant)\s+(?:with|to)|"
         r"in\s+accordance\s+with|to|of|per)")


def strip_citations(text: str) -> str:
    """Remove IS citations and the words that only introduced them: "bars conforming to IS 1786 and
    IS 432 (Part 1)." -> "bars." Leaves the product description (eval queries from real tenders)."""
    s = _CITE.sub("\0", text)
    s = re.sub(r"\0(?:\s*(?:,|/|&|\band\b|\bor\b)\s*\0)*", "\0", s)  # "IS a, IS b and IS c" -> one
    s = re.sub(rf"\b{_LEAD}\s*[:\-]?\s*\0", "", s, flags=re.I)
    s = s.replace("\0", "")
    s = re.sub(r"\(\s*\)|\[\s*\]", "", s)
    s = re.sub(r"\s+([,.;:)])", r"\1", s)
    s = re.sub(r"[,;]+(?=[.)])", "", s)  # "Philips, as per IS x." -> "Philips."
    return re.sub(r"\s+", " ", s).strip(" ,;:-")


def extract_citations(text: str) -> list[Citation]:
    out, seen = [], set()
    for m in _CITE.finditer(text):
        joint = tuple(re.findall(_JOINT, m["joint"] or ""))
        part, section = m["p1"] or m["p3"], m["s1"] or m["s2"]
        hy = re.findall(r"[A-Za-z]?\d{1,3}[A-Za-z]?", m["hy"] or "")
        if hy and part is None:
            part = hy[0]
            if len(hy) > 1 and section is None:
                section = hy[1]
        part = _arabic(part)
        year = int(m["year"] or m["year2"]) if (m["year"] or m["year2"]) else None
        key = "-".join(["IS", *joint, m["num"]])
        if part:
            key += f"-P{part}"
        if section:
            key += f"-S{section}"
        c = Citation(m.group(0).strip(), key.upper(), m["num"], part, section, year, joint)
        if (c.key, c.year) not in seen:
            seen.add((c.key, c.year))
            out.append(c)
    return out
