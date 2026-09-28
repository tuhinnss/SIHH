"""Pick ~300 standards in 3 verticals by TITLE keywords (data-driven, no IS numbers typed by hand)."""
import json
import re

from app.config import DATA, INDEX_DIR

VERTICALS = {
    "steel_cement": r"\bcement\b|steel bars|reinforc|structural steel|\bconcrete\b|aggregates?\b|wire rod|rolled steel|mortar|\bbricks?\b",
    "cables_electrical": r"\bcables?\b|conductors?\b|switchgear|lumin|\blamps?\b|electrical|wiring|insulat|\bLED\b|\bswitch|circuit.breaker|transformer",
    "pipes_plumbing": r"\bpipes?\b|plumbing|\bvalves?\b|\bfittings?\b|water supply|sanitary|cistern|\btaps?\b|\bwater closet|\bcocks?\b",
}
PRIORITY = {  # core product titles first, then newest
    "steel_cement": r"steel bars|reinforc|\bcement\b",
    "cables_electrical": r"\bcables?\b|lumin|\bLED\b",
    "pipes_plumbing": r"\bpipes?\b|water supply",
}
PER_VERTICAL = 100
# titles that are test-method / handbook noise are less useful as anchors
SKIP = re.compile(r"handbook|glossary|methods? of test|code of practice for", re.I)


def main() -> None:
    docs = json.loads((INDEX_DIR / "docs.json").read_text())
    picked: dict[str, str] = {}
    for vert, pat in VERTICALS.items():
        rx = re.compile(pat, re.I)
        cands = [d for d in docs if d["designation"] == "IS" and not d["flags"] and d["title"]
                 and rx.search(d["title"]) and not SKIP.search(d["title"]) and (d["year"] or 0) >= 1990
                 and d["identifier"] not in picked]
        pri = re.compile(PRIORITY[vert], re.I)
        cands.sort(key=lambda d: (not pri.search(d["title"]), -(d["year"] or 0), d["key"]))
        for d in cands[:PER_VERTICAL]:
            picked[d["identifier"]] = vert
    out = [{"identifier": i, "vertical": v} for i, v in picked.items()]
    (DATA / "subset_ids.json").write_text(json.dumps(out, indent=0))
    print(len(out), {v: sum(1 for o in out if o["vertical"] == v) for v in VERTICALS})


if __name__ == "__main__":
    main()
