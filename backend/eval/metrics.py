import math


def recall_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    return len(set(ranked[:k]) & gold) / len(gold) if gold else 0.0


def hit_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    """1 if any gold standard is in the top k (tender lines often cite several standards at once)."""
    return 1.0 if set(ranked[:k]) & gold else 0.0


def mrr(ranked: list[str], gold: set[str]) -> float:
    for i, r in enumerate(ranked, 1):
        if r in gold:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 1) for i, r in enumerate(ranked[:k], 1) if r in gold)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(gold), k) + 1))
    return dcg / ideal if ideal else 0.0
