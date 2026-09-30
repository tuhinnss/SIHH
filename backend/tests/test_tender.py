import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import tender  # noqa: E402
from app.analyze import analyze_pdf  # noqa: E402
from app.catalogue import CatalogueIndex, Entry  # noqa: E402
from app.certification import CertificationTable  # noqa: E402
from app.linter import Linter  # noqa: E402
from app.llm import LLMClient  # noqa: E402
from app.recommender import Recommender  # noqa: E402


def cat():
    es = {
        "IS-100": Entry("IS-100", "IS 100", "Widgets", 2008, [1985, 2008], "u"),
        "IS-200": Entry("IS-200", "IS 200", "Old gadgets", 1990, [1990], "u"),
        "IS-300": Entry("IS-300", "IS 300", "New gadgets", 2015, [2015], "u"),
        "IS-IEC-60500-P2": Entry("IS-IEC-60500-P2", "IS/IEC 60500 (Part 2)", "Switches", 2016, [2016], "u"),
        "IS-IEC-691": Entry("IS-IEC-691", "IS/IEC 691", "Thermal links", 1993, [1993], "u"),
    }
    return CatalogueIndex(es, {"IS-200": ["IS-300"]})


def cert(rows=()):
    return CertificationTable(list(rows))


def types(flags):
    return sorted(f["type"] for f in flags)


def test_linter_flags():
    L = Linter(cat(), cert())
    flags, cited = L.lint_item("Widgets as per IS 100 : 1985 and IS 200 and IS 999 : 2001")
    assert types(flags) == ["not_in_catalogue", "older_edition", "superseded"]
    assert {f["severity"] for f in flags if f["type"] == "superseded"} == {"red"}
    assert [c["in_catalogue"] for c in cited] == [True, True, False]


def test_current_edition_is_clean_and_joint_prefix_resolves():
    L = Linter(cat(), cert())
    assert L.lint_item("Widgets to IS 100 : 2008")[0] == []
    flags, cited = L.lint_item("Switches to IS 60500 (Part 2) : 2016")  # long IEC-style number cited without IEC
    assert flags == [] and cited[0]["in_catalogue"]


def test_brand_flag_and_equivalent_exemption():
    L = Linter(cat(), cert())
    assert types(L.lint_item("LED light, Make: Philips 60W")[0]) == ["brand_name"]
    assert L.lint_item("LED light, Make: Philips 60W or equivalent")[0] == []
    assert types(L.lint_item("Cable of M/s Polycab type")[0]) == ["brand_name"]
    assert L.lint_item("Steel bars 12 mm")[0] == []


ROW = {"product": "widgets", "is_number": "IS 100", "scheme": "ISI/QCO", "order_reference": "x",
       "effective_date": "2020-01-01", "withdrawn_date": "", "source_url": "", "last_verified": ""}


def test_certification_flag_only_when_table_says_and_clause_missing():
    L = Linter(cat(), cert([ROW]))
    assert types(L.lint_item("Widgets as per IS 100 : 2008")[0]) == ["no_certification"]
    assert L.lint_item("Widgets as per IS 100 : 2008, ISI marked")[0] == []
    assert L.lint_item("Gadgets as per IS 300 : 2015")[0] == []      # not in table


def test_certification_dates_respected():
    future = {**ROW, "effective_date": "2999-01-01"}
    withdrawn = {**ROW, "withdrawn_date": "2021-01-01"}
    assert cert([future]).for_is("IS 100") is None
    assert cert([withdrawn]).for_is("IS 100") is None
    assert cert([ROW]).for_is("IS 100")["scheme"] == "ISI/QCO"
    assert cert([]).for_is("IS 100") is None


def test_split_numbered_bullets_and_continuations():
    text = ("Tender No 5\n1. Supply of TMT steel bars 12 mm dia\nconforming to IS 100\n"
            "2) Supply of LED street light 60W\n• PVC pipe 110 mm for drinking water\nPage 2 of 4\n")
    items = tender.split_items(text)
    assert len(items) == 3
    assert items[0].endswith("conforming to IS 100") and "Page" not in " ".join(items)


def test_split_boq_table_layout():
    text = "S.No\nDescription\nQty\nUnit\n1\nSupply of PVC pipe 110 mm class 4\n100\nMtr\n2\nSupply of gate valve 50 mm\n10\nNos\n"
    items = tender.split_items(text)
    assert items == ["Supply of PVC pipe 110 mm class 4", "Supply of gate valve 50 mm"]


def make_pdf(lines):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 60), "\n".join(lines), fontsize=10)
    return doc.tobytes()


class Retr:
    def search(self, q, **kw):
        return [{"is_number": "IS 100", "title": "Widgets", "year": 2008, "score": 0.02,
                 "source_url": "u"}]


def test_end_to_end_pdf_analysis():
    pdf = make_pdf(["1. Supply of widgets as per IS 100 : 1985, Make: Acme", "2. Supply of gadgets conforming to IS 200"])
    catalogue = {"IS 100": {"is_number": "IS 100", "title": "Widgets", "year": 2008, "source_url": "u"}}
    rec = Recommender(Retr(), LLMClient([]), catalogue)
    out = analyze_pdf(pdf, "t.pdf", rec, Linter(cat(), cert()))
    assert out["split_method"] == "heuristic" and len(out["items"]) == 2
    assert types(out["items"][0]["flags"]) == ["brand_name", "older_edition"]
    assert types(out["items"][1]["flags"]) == ["superseded"]
    assert out["summary"] == {"red": 1, "amber": 2}
    assert out["items"][0]["recommendations"][0]["is_number"] == "IS 100"
    assert out["scanned_pages"] == 0 and out["warning"] is None


def test_scanned_pages_are_reported_not_silently_empty():
    text_page = pymupdf.open(stream=make_pdf(["1. Supply of widgets as per IS 100", "2. Supply of gadgets"]))
    scan = pymupdf.open()
    page = scan.new_page()
    page.insert_image(page.rect, pixmap=text_page[0].get_pixmap(dpi=100))  # image only, no text layer
    rec = Recommender(Retr(), LLMClient([]), {})
    out = analyze_pdf(scan.tobytes(), "scan.pdf", rec, Linter(cat(), cert()))
    assert out["items"] == [] and out["scanned_pages"] == 1
    assert "1 of 1 page(s) are scanned" in out["warning"]


def test_max_items_truncation():
    pdf = make_pdf([f"{i}. Supply of item number {i} widgets" for i in range(1, 8)])
    rec = Recommender(Retr(), LLMClient([]), {"IS 100": {"is_number": "IS 100", "title": "W", "year": 1, "source_url": "u"}})
    out = analyze_pdf(pdf, "t.pdf", rec, Linter(cat(), cert()), max_items=3)
    assert out["truncated"] and len(out["items"]) == 3 and out["total_items_found"] == 7
    assert out["next_offset"] == 3
    # next pages continue the numbering; the last page has no next_offset
    page2 = analyze_pdf(pdf, "t.pdf", rec, Linter(cat(), cert()), max_items=3, offset=3)
    assert [it["index"] for it in page2["items"]] == [4, 5, 6] and page2["next_offset"] == 6
    last = analyze_pdf(pdf, "t.pdf", rec, Linter(cat(), cert()), max_items=3, offset=6)
    assert [it["index"] for it in last["items"]] == [7] and not last["truncated"] and last["next_offset"] is None
    assert "item number 7" in last["items"][0]["text"]


def test_short_numbers_do_not_match_prefixed_standards():
    L = Linter(cat(), cert())
    flags, cited = L.lint_item("Cables to IS 691 : 1988")     # plain IS 691 is NOT IS/IEC 691
    assert not cited[0]["in_catalogue"] and types(flags) == ["not_in_catalogue"]


# Shape of a GeM "Bid Document" (English markers only; Hindi labels extract garbled)
GEM_LINES = [
    "Bid Number: GEM/2026/B/1234567",
    "Ministry/State Name Some State",
    "Searched String: 40MM HDPE PIPE",
    "Old gadgets conforming to IS 200, Towels Conforming To IS 100 (V4)",
    "Relevant Categories selected for notification",
    "1. The minimum average annual financial turnover of the bidder shall be as indicated.",
    "40MM DIA HDPE PIPE",
    "xyz /Technical Specifications",
    "Specification Document",  # real PDFs: link-table cells on separate lines
    "View File",
    "BOQ Detail Document View File",
    "Advisory-Please refer attached BOQ document for detailed consignee list and delivery period.",
    "xyz/Consignees/Reporting Officer and Quantity",
    "1 Some Officer",
    "5 15",
    "6 / 13",
    "Gadget Cable 4 Core",
    "(hindi text /Minimum 50% and 20% Local",  # Make-in-India note between heading and marker
    "Content required for qualifying as Class 1 and Class 2 Local Supplier respectively)",
    "xyz /Technical Specifications",
    "Conductor Copper, conforming to IS 300",
    "xyz/Consignees/Reporting Officer and Quantity",
    "1 Some Officer",
    "800 15",
]


GEM_CATEGORY_LINES = [  # GeM category bid: wrapped heading, fields, parameter table
    "Bid Number: GEM/2025/B/7654321",
    "4. Short Duration Bid has been published by the Buyer.",
    "Widget Luminaire For Roads (V2) Conforming To IS 300 (Part 5 /",
    "Section 3) ( 40 pieces )",
    "(Minimum 50% and 20% Local Content required for qualifying as Class 1 and Class 2 Local Supplier",
    "respectively/hindi)",
    "Bis Required",
    "Yes",
    "Technical Specifications/hindi",
    "Specification",
    "Specification Name/hindi",
    "Bid Requirement/hindi (Allowed",
    "Values)/hindi",
    "Rated power 70 W",
    "Consignees/Reporting Officer/hindi and/ Quantity",
]


def test_gem_category_bid_heading_wraps_and_fields_are_skipped():
    assert tender.gem_items("\n".join(GEM_CATEGORY_LINES)) == [
        "Widget Luminaire For Roads Conforming To IS 300 (Part 5 / Section 3) Rated power 70 W"]


def test_gem_items_are_headings_plus_their_specs():
    assert tender.gem_items("\n".join(GEM_LINES)) == [
        "40MM DIA HDPE PIPE", "Gadget Cable 4 Core Conductor Copper, conforming to IS 300"]
    assert tender.gem_items("1. Supply of widgets as per IS 100") == []  # not a GeM bid


def test_gem_bid_ignores_gem_suggestion_box_and_forms():
    rec = Recommender(Retr(), LLMClient([]), {"IS 100": {"is_number": "IS 100", "title": "W", "year": 1, "source_url": "u"}})
    out = analyze_pdf(make_pdf(GEM_LINES), "gem.pdf", rec, Linter(cat(), cert()))
    assert out["split_method"] == "gem" and [it["text"][:18] for it in out["items"]] == ["40MM DIA HDPE PIPE", "Gadget Cable 4 Cor"]
    # IS 200 (superseded) and IS 100 appear only in GeM's suggestion box -> no flags from them
    assert [[c["raw"] for c in it["cited"]] for it in out["items"]] == [[], ["IS 300"]]
    assert out["summary"] == {"red": 0, "amber": 0}
