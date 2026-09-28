import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.metrics import mrr, ndcg_at_k, recall_at_k  # noqa: E402


def test_recall_mrr_ndcg():
    ranked = ["a", "b", "c", "d"]
    gold = {"b", "d", "z"}
    assert recall_at_k(ranked, gold, 2) == 1 / 3
    assert recall_at_k(ranked, gold, 4) == 2 / 3
    assert mrr(ranked, gold) == 0.5
    assert mrr(["x"], gold) == 0.0
    dcg = 1 / math.log2(3) + 1 / math.log2(5)
    ideal = 1 + 1 / math.log2(3) + 1 / math.log2(4)
    assert abs(ndcg_at_k(ranked, gold, 10) - dcg / ideal) < 1e-9
    assert ndcg_at_k(["a"], set(), 10) == 0.0
