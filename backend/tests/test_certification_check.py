import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_pipeline.check_certification import REQUIRED, check  # noqa: E402

H = ",".join(REQUIRED)


def write(tmp_path, body):
    p = tmp_path / "c.csv"
    p.write_text(H + "\n" + body)
    return p


def test_empty_template_ok(tmp_path):
    assert check(write(tmp_path, "")) == []


def test_valid_row(tmp_path):
    p = write(tmp_path, "widgets,IS 100,ISI/QCO,ord,2020-01-01,,https://bis.gov.in/x,2026-01-01\n")
    assert check(p) == []


def test_problems_reported(tmp_path):
    p = write(tmp_path, "w,IS 100,MAYBE,ord,01/02/2020,,notaurl,\n")
    msgs = " | ".join(check(p))
    assert "scheme" in msgs and "effective_date" in msgs and "source_url" in msgs and "last_verified" in msgs


def test_bad_header(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("a,b\n")
    assert "header" in check(p)[0]
