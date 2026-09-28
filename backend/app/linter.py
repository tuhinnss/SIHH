"""Tender Linter. Flags per line item:
  superseded (red)      cited IS is superseded per our edges
  no_certification (red) certification.csv says a mark is needed but the item has no such clause
  not_in_catalogue (amber) cited IS not found in our (older) catalogue -> verify on BIS
  older_edition (amber) cited year older than the catalogue's latest
  brand_name (amber)    brand/make wording in the spec (restrictive, GFR-unfriendly)
Everything is "as per our catalogue"; messages say so."""
import re

from app.catalogue import CatalogueIndex
from app.certification import CertificationTable
from app.citations import Citation, extract_citations

# Pattern-based (no brand list from memory): trademarks, "make/brand: X", "M/s X".
_BRAND = [
    re.compile(r"[®™]"),
    re.compile(r"\b(?:brand|make|manufacturer|mfr\.?|model(?:\s*no\.?)?)\s*[:\-]\s*[A-Z][\w&.\- ]{1,30}", re.I),
    re.compile(r"\bof\s+M/s\.?\s+[A-Z][\w&.\-]+"),
    re.compile(r"\b(?:only|strictly)\s+(?:of\s+)?[A-Z][a-z]+\s+(?:brand|make)\b", re.I),
]
_EQUIV = re.compile(r"or\s+(?:equivalent|equal|similar)|equivalent\s+make", re.I)
_CERT_WORDS = re.compile(
    r"\bISI\b|\bBIS\b|\bIS\s*mark|standard\s*mark|\bCRS\b|hallmark|\bHUID\b|\blicen[cs]e\b|"
    r"registration|certif(?:ied|icate|ication)|QCO", re.I)


def flag(ftype, severity, message, **extra):
    return {"type": ftype, "severity": severity, "message": message, **extra}


class Linter:
    def __init__(self, catalogue: CatalogueIndex, cert: CertificationTable):
        self.cat, self.cert = catalogue, cert

    def cited(self, text: str) -> list[tuple[Citation, object]]:
        return [(c, self.cat.resolve(c)) for c in extract_citations(text)]

    def lint_item(self, text: str, top_primary: dict | None = None) -> tuple[list[dict], list[dict]]:
        """Returns (flags, cited_info). `top_primary` is the top recommended card, if any."""
        flags, cited_info, cited_is = [], [], []
        for c, e in self.cited(text):
            info = {"raw": c.raw, "key": c.key, "year": c.year,
                    "in_catalogue": e is not None, "latest_year": e.latest_year if e else None}
            cited_info.append(info)
            if e is None:
                flags.append(flag("not_in_catalogue", "amber",
                                  f"{c.raw} is not in our catalogue (older archive snapshot). "
                                  "Verify on BIS Know Your Standards.", ref=c.raw))
                continue
            cited_is.append(e.is_number)
            newer = self.cat.superseded_by.get(e.key)
            if newer:
                names = ", ".join(self.cat.entries[k].is_number if k in self.cat.entries else k
                                  for k in newer)
                flags.append(flag("superseded", "red",
                                  f"{c.raw} is superseded by {names} per our records.", ref=c.raw))
            if c.year and e.latest_year and c.year < e.latest_year:
                flags.append(flag("older_edition", "amber",
                                  f"{c.raw}: cited edition is {c.year}, but our catalogue lists {e.latest_year} "
                                  "as the latest edition (verify on BIS).", ref=c.raw))
        if any(p.search(text) for p in _BRAND) and not _EQUIV.search(text):
            flags.append(flag("brand_name", "amber",
                              "Spec appears to name a brand/make without 'or equivalent' — may "
                              "restrict competition."))
        needs = {r["scheme"] or "certification" for n in cited_is if (r := self.cert.for_is(n))}
        if top_primary and top_primary.get("certification"):
            needs.add(top_primary["certification"].get("scheme") or "certification")
        for r in self.cert.for_text(text):
            needs.add(r.get("scheme") or "certification")
        if needs and not _CERT_WORDS.search(text):
            flags.append(flag("no_certification", "red",
                              f"Certification required per our table ({', '.join(sorted(needs))}) "
                              "but no certification clause found in this item."))
        return flags, cited_info
