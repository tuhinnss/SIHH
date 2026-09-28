import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_pipeline.refs_parsing import find_refs, find_scope, find_supersedes, parse_bare_list  # noqa: E402

# Synthetic text that mimics the column-wise OCR layout of an Annex reference list.
ANNEX = """
1 SCOPE

1.1 This standard covers requirements for widgets used in testing of things, and it is long enough to pass the length filter.

14

IS No.
4669 : 1968

4905 : 2015/
ISO 24153 : 2009

12235

(Part 1) : 2004
(Part 2) : 2004

ANNEX A
( Clause 2)
LIST OF REFERRED INDIAN STANDARDS

Title
Some titles here
which are not numbers

15
IS No.
(Part 5/Sec 1) :
2004

12818 : 2010
IS 9999 : 2021
ANNEX B
9999
"""


def keys(refs):
    return [r["key"] for r in refs]


def test_bare_list_columns_parts_sections_and_page_numbers():
    ks = keys(find_refs(ANNEX))
    assert "IS-4669" in ks and "IS-4905" in ks          # 'IS-ISO' pair: leading number only
    assert "IS-12235-P1" in ks and "IS-12235-P2" in ks
    assert "IS-12235-P5-S1" in ks                        # part on a page continuation, year wrapped
    assert "IS-12818" in ks
    assert "IS-14" not in ks and "IS-15" not in ks       # page numbers ignored
    assert "IS-2004" not in ks                           # year-only line not a standard
    assert "IS-9999" in ks                               # prefixed cite (running footer) also found


def test_stops_at_next_annex():
    assert "IS-9999" in keys(find_refs(ANNEX))  # from IS-prefixed line before ANNEX B
    # the bare '9999' after ANNEX B has no year/parts anyway; region must not extend past it
    assert keys(find_refs(ANNEX)).count("IS-9999") == 1


def test_inline_references_clause_old_style():
    text = ("2. REFERENCES\n\n2.1 The following standards are necessary adjuncts:\n"
            "IS 1554 (Part 1) : 1988 Cables\nIS/IEC 60947-2 : 2016 Switchgear\n\n3. TERMINOLOGY\nIS 5555 : 1990\n")
    ks = keys(find_refs(text))
    assert ks == ["IS-1554-P1", "IS-IEC-60947-P2"]


def test_scope_snippet_skips_toc_and_truncates():
    toc = "SCOPE\n\n2 REFERENCES\n"
    body = "1 SCOPE\n\n" + "covers x " * 200
    s = find_scope(toc + body)
    assert s and len(s) <= 800 and s.startswith("covers x")


def test_supersedes_from_titles_and_prose():
    assert keys(find_supersedes("Luminaires (Superseding IS 1502, 2135)")) == ["IS-1502", "IS-2135"]
    assert keys(find_supersedes("Coal [superseding IS 1351:1959]")) == ["IS-1351"]
    assert keys(find_supersedes("Foreword. This standard supersedes IS 4985 : 2000 and IS 777.\n\nNext para IS 12 : 1990")) \
        == ["IS-4985", "IS-777"]
    assert find_supersedes("A standard about pipes") == []


def test_parse_bare_list_requires_header():
    assert parse_bare_list("4669 : 1968\n") == []      # numbers before any 'IS No.' header ignored


def test_inline_rows_under_normative_references_with_ocr_noise():
    text = ("2  NORMATIVE  REFERENCES\n\nThe following standards contain provisions.\n\nIS No. Title\n\n"
            "1239:2004 Steel tubes, tubulars\nwrought steel fittings\n\n2062 :2011 Hot rolled steel\n\n"
            "2828  ;  1964        Glossary of terms\n\n12235 (Part 1) : 2004 Methods\n\n"
            "3  TERMINOLOGY\n\n4444 : 1999 not a reference\n")
    ks = keys(find_refs(text))
    assert ks == ["IS-1239", "IS-2062", "IS-2828", "IS-12235-P1"]


def test_negated_supersede_ignored():
    assert find_supersedes("This standard does not supersede IS 1234 : 1980.") == []
    assert [r["key"] for r in find_supersedes("This standard supersedes IS 1234 : 1980.")] == ["IS-1234"]


def test_scope_trimmed_at_next_clause():
    from data_pipeline.refs_parsing import trim_scope
    flat = "1.1 This standard covers pipes. 1.2 It does not cover pumps, see IS 12231. 2 REFERENCES The standards listed in Annex A"
    assert trim_scope(flat) == "1.1 This standard covers pipes. 1.2 It does not cover pumps, see IS 12231."
    assert trim_scope("1.1 covers x for 2 mm pipes and 3 Nos") == "1.1 covers x for 2 mm pipes and 3 Nos"
