import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config  # noqa: E402
from app.clause import tender_clause  # noqa: E402
from app.llm import LLMClient, LLMUnavailable, StubProvider  # noqa: E402
from app.recommender import Recommender, select_schema  # noqa: E402
from app.validator import validate_selection  # noqa: E402


def row(num, title, year=2000):
    return {"is_number": num, "title": title, "year": year, "score": 0.03,
            "source_url": f"https://example.org/{num.replace(' ', '')}"}


DOCS = [row("IS 1786", "High strength deformed steel bars", 2008),
        row("IS 432 (Part 1)", "Mild steel bars for concrete reinforcement", 1982),
        row("IS 4985", "Unplasticized PVC pipes for potable water", 2021)]


class FakeRetriever:
    def __init__(self):
        self.calls = []

    def search(self, query, **kw):
        self.calls.append((query, kw))
        return [dict(d) for d in DOCS]


def make(responder, catalogue=None):
    r = FakeRetriever()
    cat = catalogue if catalogue is not None else {d["is_number"]: d for d in DOCS}
    return Recommender(r, LLMClient([StubProvider(responder)]), cat), r


def test_validator_drops_invented_and_duplicates(tmp_path, monkeypatch):
    monkeypatch.setattr("app.validator.INVENTED_LOG", tmp_path / "log.jsonl")
    items = [{"is_number": "IS 1786"}, {"is_number": "IS 99999"}, {"is_number": "IS 1786"},
             {"is_number": "IS 4985"}, {"is_number": None}]
    valid, dropped = validate_selection(items, {"IS 1786", "IS 4985", "IS 555"},
                                        {"IS 1786", "IS 4985"})
    assert [v["is_number"] for v in valid] == ["IS 1786", "IS 4985"]
    assert [d["drop_reason"] for d in dropped] == ["not_in_candidates", "duplicate", "not_in_candidates"]
    assert "IS 99999" in (tmp_path / "log.jsonl").read_text()


def test_validator_drops_candidate_missing_from_catalogue(tmp_path, monkeypatch):
    monkeypatch.setattr("app.validator.INVENTED_LOG", tmp_path / "log.jsonl")
    valid, dropped = validate_selection([{"is_number": "IS 555"}], {"IS 555"}, set())
    assert not valid and dropped[0]["drop_reason"] == "not_in_catalogue"


def test_schema_enum_is_candidates_only():
    s = select_schema(["IS 1", "IS 2"])
    assert s["properties"]["selected"]["items"]["properties"]["is_number"]["enum"] == ["IS 1", "IS 2"]


def _respond(prompt, schema):
    if "english_query" in schema["properties"]:
        return {"english_query": "TMT steel bars for RCC",
                "search_terms": ["high strength deformed steel bars for concrete reinforcement"]}
    return {"selected": [
        {"is_number": "IS 1786", "relevance": "primary", "reason": "Deformed bars.", "confidence": 0.9},
        {"is_number": "IS 77777", "relevance": "primary", "reason": "Made up.", "confidence": 0.99},
        {"is_number": "IS 432 (Part 1)", "relevance": "allied", "reason": "Older bars.", "confidence": 1.7},
    ]}


def test_invented_number_never_reaches_output(tmp_path, monkeypatch):
    monkeypatch.setattr("app.validator.INVENTED_LOG", tmp_path / "log.jsonl")
    rec, retr = make(_respond)
    out = rec.recommend("TMT steel bars for RCC")
    nums = [r["is_number"] for r in out["results"]]
    assert nums == ["IS 1786", "IS 432 (Part 1)"] and out["dropped_invalid"] == 1
    assert out["llm_used"] and out["results"][1]["confidence"] == 1.0  # clamped
    assert out["results"][0]["clause"].startswith("The material/equipment supplied shall conform to IS 1786 : 2008")
    # expansion terms were passed to retrieval as extra queries
    assert retr.calls[0][1]["extra_queries"] == ["high strength deformed steel bars for concrete reinforcement"]


def test_hindi_original_text_is_also_embedded(tmp_path, monkeypatch):
    monkeypatch.setattr("app.validator.INVENTED_LOG", tmp_path / "log.jsonl")
    rec, retr = make(_respond)
    rec.recommend("टीएमटी सरिया")
    assert retr.calls[0][0] == "TMT steel bars for RCC"
    assert "टीएमटी सरिया" in retr.calls[0][1]["extra_queries"]


def test_llm_down_falls_back_to_retrieval():
    def boom(prompt, schema):
        raise RuntimeError("quota")
    rec, _ = make(boom)
    out = rec.recommend("anything")
    assert not out["llm_used"] and len(out["results"]) == 3
    assert all(r["reason"] is None for r in out["results"])


def test_no_providers_falls_back():
    r = FakeRetriever()
    out = Recommender(r, LLMClient([]), {d["is_number"]: d for d in DOCS}).recommend("x")
    assert not out["llm_used"] and len(out["results"]) == 3


def test_all_invalid_selection_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr("app.validator.INVENTED_LOG", tmp_path / "log.jsonl")

    def bad(prompt, schema):
        if "english_query" in schema["properties"]:
            return {"english_query": "x", "search_terms": []}
        return {"selected": [{"is_number": "IS 1", "relevance": "primary", "reason": "", "confidence": 1}]}
    out = make(bad)[0].recommend("x")
    assert not out["llm_used"] and out["dropped_invalid"] == 1


def test_llm_client_falls_through_providers():
    def boom(p, s):
        raise RuntimeError("x")
    c = LLMClient([StubProvider(boom), StubProvider(lambda p, s: {"ok": 1})])
    assert c.generate_json("p", {}) == {"ok": 1}
    try:
        LLMClient([StubProvider(boom)]).generate_json("p", {})
        assert False
    except LLMUnavailable:
        pass


def test_clause_uses_only_given_fields():
    c = tender_clause("IS 4985", None, "PVC pipes -")
    assert "IS 4985" in c and "(PVC pipes)" in c and " : None" not in c
