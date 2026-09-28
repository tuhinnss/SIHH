import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.citations import extract_citations  # noqa: E402


@pytest.mark.parametrize("text,key,year", [
    ("IS 1554 (Part 1) : 1988", "IS-1554-P1", 1988),
    ("as per IS/IEC 60947-2 : 2016.", "IS-IEC-60947-P2", 2016),
    ("IS 1239 (Pt 1)", "IS-1239-P1", None),
    ("IS:456-2000 plain", "IS-456", 2000),
    ("IS 456:2000", "IS-456", 2000),
    ("IS 12970-3-2:1992", "IS-12970-P3-S2", 1992),
    ("IS 12970 (Part 3/Sec 2)", "IS-12970-P3-S2", None),
    ("IS 16107 (Part 2) (Sec 2) : 2017", "IS-16107-P2-S2", 2017),
    ("IS/ISO/IEC 17799 : 2005", "IS-ISO-IEC-17799", 2005),
    ("conforming to IS 1786.", "IS-1786", None),
])
def test_normalise(text, key, year):
    (c,) = extract_citations(text)
    assert (c.key, c.year) == (key, year)


def test_multiple_and_dedup():
    cs = extract_citations("IS 1786 : 2008, IS 1786 : 2008 and IS 432 (Part 1) : 1982")
    assert [c.key for c in cs] == ["IS-1786", "IS-432-P1"]


def test_no_false_positives():
    assert extract_citations("This is 5 kg of the item; his 123 units; it is 100 percent") == []
    assert extract_citations("Quantity 250 nos, Rate 1554") == []
