import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_pipeline.parsing import parse_item  # noqa: E402


def p(ident, title):
    return parse_item({"identifier": f"gov.in.is.{ident}", "title": title})


def test_simple():
    s = p("104.1979", "IS 104: Ready mixed paint, brushing, zinc chrome, priming")
    assert (s.key, s.is_number, s.year) == ("IS-104", "IS 104", 1979)
    assert s.title.startswith("Ready mixed paint")


def test_year_from_identifier_not_date():
    s = p("4811.2014", "IS 4811 : 2014: Cinnamon Whole - Specification")
    assert s.year == 2014 and s.title == "Cinnamon Whole - Specification"


def test_part_and_section():
    s = p("12970.3.2.1992", "IS 12970-3-2: Semiconductor devices, Part 3: X, Section 2: Static")
    assert (s.key, s.part, s.section) == ("IS-12970-P3-S2", "3", "2")
    assert s.is_number == "IS 12970 (Part 3) (Sec 2)"


def test_title_header_with_part_and_year():
    s = p("1783.2.2014", "IS 1783 : Part 2 : 2014: Drums, Large, Fixed Ends - Specification Part 2")
    assert s.title.startswith("Drums, Large") and s.part == "2"


def test_joint_prefix():
    s = p("iso.iec.17799.2005", "IS/ISO/IEC 17799: Information Technology_ Code of practice")
    assert s.key == "IS-ISO-IEC-17799" and s.designation == "IS/ISO/IEC"


def test_alnum_part_and_flags():
    assert p("iso.105.A01.1994", "IS/ISO 105-A01: Textiles").part == "A01"
    s = p("10001.h.1981", "IS 10001: Engines (Hindi Edition)")
    assert s.flags == ["hindi"] and s.key == "IS-10001"


def test_other_families():
    s = p("sp.15.1.1989", "SP 15-1: Handbook of Textile Testing, Part 1: Testing")
    assert s.key == "SP-15-P1" and s.designation == "SP"
    assert p("guide.14.2003", "IS/ISO/IEC Guide 14: Purchase information").designation == "IS/ISO/IEC Guide"


def test_non_catalogue_id_ignored():
    assert parse_item({"identifier": "something.else", "title": "x"}) is None


def test_mojibake_repaired():
    s = p("17482.2020", "IS 17482: Drinking Water Supply Management System \u00e2\u20ac\u201c Requirements")
    assert "\u2013" in s.title and "\u00e2" not in s.title
