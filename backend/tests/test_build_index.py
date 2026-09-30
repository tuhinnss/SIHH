import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_pipeline.build_index import bm25_text, doc_text  # noqa: E402


def test_scope_snippet_goes_to_dense_text_only():
    r = {"is_number": "IS 100", "title": "Widgets", "scope_snippet": "1.1 This standard covers widgets."}
    assert bm25_text(r) == "IS 100: Widgets"  # equal footing with the title-only majority for BM25
    assert doc_text(r) == "IS 100: Widgets. 1.1 This standard covers widgets."
    assert doc_text({**r, "scope_snippet": None}) == bm25_text(r)
