import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_pipeline.build_edges import classify, plausible  # noqa: E402


def test_classify_by_target_title():
    assert classify("Methods of test for PVC resins") == "test_method"
    assert classify("Thermoplastics pipes and fittings - Methods of Test") == "test_method"
    assert classify("Glossary of terms used in plastics") == "terminology"
    assert classify("Unplasticized PVC pipes for potable water") == "normative_ref"


def test_foreword_supersession_plausibility():
    assert plausible("Elastomer insulated flexible cables for use in mines", "Rubber insulated cables")
    assert not plausible("Elastomer insulated flexible cables for use in mines", "Thermal Links - Requirements")
