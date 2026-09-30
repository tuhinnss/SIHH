import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.from_tenders import rows_from_text  # noqa: E402

TEXT = """SCHEDULE OF REQUIREMENTS
1. Supply of widgets, 20 mm, conforming to IS 100 : 1985
2. Supply of gadgets as per IS 200 (Part 1) and IS 300
3. Bidder shall submit EMD along with the bid
4. Cable IS:400
"""


def test_cited_items_become_rows_with_citations_removed():
    rows = rows_from_text(TEXT, "t.pdf")
    assert [(r["query"], r["gold_is"]) for r in rows] == [
        ("Supply of widgets, 20 mm", ["IS 100 : 1985"]),
        ("Supply of gadgets", ["IS 200 (Part 1)", "IS 300"]),
    ]  # item 3 cites nothing; item 4 leaves too little text to be a query
    assert rows[0]["source"] == "t.pdf#item1" and rows[0]["lang"] == "en"
