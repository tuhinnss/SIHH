import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_pipeline.qco_orders import (apply_term, dates_in, force_sentences, norm_is, parse_rows,  # noqa: E402
                                      publication_date, schedule_terms)

# Shape of the saved bis.gov.in page: truncated serial, IS number (may wrap), product, blank (nbsp) line;
# "(namely IS ...)" lists belong to the order column and are not product rows.
PAGE = """.
IS 100
Widgets for water supply
\xa0
1. Widgets (Quality
Control)Order, 2003
Extension in date of
enforcement Order
(namely IS 900, IS 901)
0.
IS 200 (Part
1)
Gadgets-Part1 fly-ash based
\xa0
1.
IS 300 : Part
2:1982
Mild gadget bars
\xa0
2.
IS 400
: 1988 Specification for PVC gadgets
\xa0
3.
IS 500 (Part 2/Sec 3)
Safety of widgets - irons
\xa0
4.
IS 600 (Part
1 & 2) Self ballasted widgets
\xa0
"""


def test_parse_rows_handles_wrapped_numbers_and_skips_order_column():
    rows = parse_rows(PAGE)
    assert [(r["key"], r["product"]) for r in rows] == [
        ("IS-100", "Widgets for water supply"), ("IS-200-P1", "Gadgets-Part1 fly-ash based"),
        ("IS-300-P2", "Mild gadget bars"), ("IS-400", "Specification for PVC gadgets"),
        ("IS-500-P2-S3", "Safety of widgets - irons"),
        ("IS-600-P1", "Self ballasted widgets"), ("IS-600-P2", "Self ballasted widgets")]


def test_norm_is():
    assert norm_is("IS 432 : Part 1:1982") == "IS 432 (Part 1):1982"
    assert norm_is("IS 1489 (Part 1)") == "IS 1489 (Part 1)"


def test_force_sentences_and_dates():
    order = ("1. (1) This Order may be called the Widgets (Quality Control) Order, 2024. (2) It shall come into "
             "force on the date of its publication in the Official Gazette. 2. Compulsory use of Standard Mark: "
             "goods shall conform to IS 100 and this paragraph shall come into force on the 24th day of June, 2025.")
    ss = force_sentences(order)
    assert len(ss) == 2 and dates_in(ss[0]) == [] and dates_in(ss[1]) == [date(2025, 6, 24)]
    assert dates_in("Date of Implementation 01/02/2018") == [date(2018, 2, 1)]
    assert dates_in("come into force on the 13th June, 2021") == [date(2021, 6, 13)]
    assert dates_in("amended on 31/02/2020") == []  # impossible dates are ignored


# Shape of a QCO schedule table (gazette header, then per-standard rows with a start term)
ORDER = """hindi text, 22 July 2019 (an older order referred to)
MINISTRY OF WIDGETS ORDER New Delhi, the 31st January, 2020 S.O. 123(E).
Schedule
IS 100 : 2008 Widgets - Specification 72171010 With immediate effect
IS 200 : 1990 Gadgets for roads 72149990 1 month from date of publication of this Order
IS 300 : Part 1 : 1982 Bars 72131090 90 days from the date of publication"""


def test_schedule_terms_and_start_dates():
    pub = publication_date(ORDER)
    terms = schedule_terms(ORDER)
    assert pub == date(2020, 1, 31)
    assert terms == {"IS-100": "With immediate effect", "IS-200": "1 month from date of publication",
                     "IS-300-P1": "90 days from the date of publication"}
    assert apply_term(terms["IS-100"], pub) == date(2020, 1, 31)
    assert apply_term(terms["IS-200"], pub) == date(2020, 2, 29)  # clamped to the month end, never earlier
    assert apply_term(terms["IS-300-P1"], pub) == date(2020, 4, 30)
    assert apply_term("With immediate effect", None) is None  # unknown order date -> no guess
    # the Gazette masthead (date of publication) wins over the signing date
    assert publication_date("NEW DELHI, WEDNESDAY, FEBRUARY 19, 2020/MAGHA 30, 1941 " + ORDER) == date(2020, 2, 19)
    assert publication_date("referring to the order of 22 July 2019 only") is None
