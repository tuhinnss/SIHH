"""Find IS citations in free text and normalise them to catalogue keys (year ignored).

Handles e.g. "IS 1554 (Part 1) : 1988", "IS/IEC 60947-2 : 2016", "IS 1239 (Pt 1)",
"IS:456-2000", "IS 12970 (Part 3/Sec 2)". Keys follow data_pipeline.parsing:
IS-[JOINT-]{num}[-P{part}][-S{sec}].
"""
import re
from dataclasses import dataclass

_JOINT = r"(?:ISO|IEC|IEEE|TR|TS|PAS)"
_CITE = re.compile(
    rf"""(?<![A-Za-z])IS(?P<joint>(?:\s*/\s*{_JOINT})*)\s*[:\-]?\s*(?P<num>\d{{1,6}})
        (?:\s*\(\s*(?:Part|Pt)\.?\s*(?P<p1>[A-Za-z]?\d+[A-Za-z]?)\s*(?:[/,\-]\s*(?:Sec(?:tion)?\.?\s*)?(?P<s1>\d+))?\s*\))?
        (?:\s*\(\s*(?:Sec(?:tion)?\.?)\s*(?P<s2>\d+)\s*\))?
        (?P<hy>(?:\s*-\s*[A-Za-z]?\d{{1,3}}[A-Za-z]?(?!\d))*)
        (?:\s*[:\-/]\s*(?P<year>(?:19|20)\d{{2}})(?!\d))?""",
    re.X)


@dataclass(frozen=True)
class Citation:
    raw: str
    key: str
    number: str
    part: str | None
    section: str | None
    year: int | None
    joint: tuple[str, ...]


def extract_citations(text: str) -> list[Citation]:
    out, seen = [], set()
    for m in _CITE.finditer(text):
        joint = tuple(re.findall(_JOINT, m["joint"] or ""))
        part, section = m["p1"], m["s1"] or m["s2"]
        hy = re.findall(r"[A-Za-z]?\d{1,3}[A-Za-z]?", m["hy"] or "")
        if hy and part is None:
            part = hy[0]
            if len(hy) > 1 and section is None:
                section = hy[1]
        year = int(m["year"]) if m["year"] else None
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
