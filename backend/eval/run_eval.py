"""Evaluate retrieval setups on eval/eval_set.jsonl -> markdown table.

Setups: BM25 only | dense only | hybrid (RRF) | hybrid + rerank + LLM.
Rows with empty gold_is are skipped (fill them from real tenders). Gold IS numbers may be written
"IS 1786", "IS 1786 : 2008" etc.; they are normalised to catalogue keys, and unknown ones are
reported (never guessed).
Usage: python -m eval.run_eval [--file eval/eval_set.jsonl] [--k 10]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.catalogue import CatalogueIndex  # noqa: E402
from app.graph import Graph  # noqa: E402
from app.llm import LLMClient  # noqa: E402
from app.recommender import Recommender  # noqa: E402
from app.retrieval import Retriever  # noqa: E402
from eval.metrics import mrr, ndcg_at_k, recall_at_k  # noqa: E402


def load_rows(path: Path, graph: Graph):
    rows, unknown, skipped = [], [], 0
    for line in open(path, encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        if not r["gold_is"]:
            skipped += 1
            continue
        gold = set()
        for g in r["gold_is"]:
            k = graph.find_key(g)
            (gold.add(k) if k else unknown.append(g))
        if gold:
            rows.append({"query": r["query"], "lang": r.get("lang", "en"), "gold": gold})
    return rows, unknown, skipped


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(Path(__file__).with_name("eval_set.jsonl")))
    ap.add_argument("--k", type=int, default=10)
    a = ap.parse_args()

    retr = Retriever()
    cat = CatalogueIndex.from_sqlite()
    graph = Graph.from_sqlite(cat)
    rows, unknown, skipped = load_rows(Path(a.file), graph)
    print(f"{len(rows)} evaluable rows, {skipped} skipped (empty gold_is), "
          f"{len(unknown)} unknown gold IS: {unknown}\n")
    if not rows:
        print("Fill gold_is in eval_set.jsonl to get metrics.")
        return

    llm = LLMClient.from_env()
    rec = Recommender(retr, llm, {d["is_number"]: d for d in retr.docs}, graph=graph)
    catalogue_keys = {d["key"] for d in retr.docs}
    setups = {
        "BM25 only": lambda q: [h["key"] for h in retr.search(q, top_k=a.k, mode="bm25")],
        "Dense only": lambda q: [h["key"] for h in retr.search(q, top_k=a.k, mode="dense")],
        "Hybrid (RRF)": lambda q: [h["key"] for h in retr.search(q, top_k=a.k, mode="hybrid")],
    }
    invented = 0
    llm_rejected = 0

    def full(q):
        nonlocal invented, llm_rejected
        out = rec.recommend(q, top_k=a.k, rerank=True)
        keys = [c["key"] for c in out["results"]]
        invented += sum(1 for k in keys if k not in catalogue_keys)
        llm_rejected += out["dropped_invalid"]
        return keys
    have_llm = bool(llm.providers)
    setups["Hybrid + rerank + LLM" + ("" if have_llm else " (no LLM keys: rerank only)")] = full

    lines = ["| Setup | Recall@5 | Recall@10 | MRR | nDCG@10 |", "|---|---|---|---|---|"]
    for name, fn in setups.items():
        r5 = r10 = m = n = 0.0
        for row in rows:
            ranked = fn(row["query"])
            r5 += recall_at_k(ranked, row["gold"], 5)
            r10 += recall_at_k(ranked, row["gold"], 10)
            m += mrr(ranked, row["gold"])
            n += ndcg_at_k(ranked, row["gold"], 10)
        c = len(rows)
        lines.append(f"| {name} | {r5 / c:.3f} | {r10 / c:.3f} | {m / c:.3f} | {n / c:.3f} |")
    print("\n".join(lines))
    print(f"\nInvented IS numbers in final output: {invented} (must be 0). "
          f"LLM proposals rejected by the validator: {llm_rejected}.")
    sys.exit(1 if invented else 0)


if __name__ == "__main__":
    main()
