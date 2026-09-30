"""Hybrid retrieval: BM25 + dense (RRF fusion), optional cross-encoder rerank."""
import json
import threading

import bm25s
import numpy as np

from app.config import EMBED_MODEL, INDEX_DIR, RERANK_MODEL

RRF_K = 60


def rrf(rankings: list[list[int]], k: int = RRF_K) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return scores


class Retriever:
    def __init__(self) -> None:
        self.docs: list[dict] = json.loads((INDEX_DIR / "docs.json").read_text(encoding="utf-8"))
        self.bm25 = bm25s.BM25.load(str(INDEX_DIR / "bm25"))
        self.emb = np.load(INDEX_DIR / "emb.npy")
        self._model = None
        self._reranker = None
        self._lock = threading.Lock()

    @property
    def model(self):
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer
                try:  # cached copy first: skips the Hugging Face online check (~10 s here)
                    self._model = SentenceTransformer(EMBED_MODEL, device="cpu", local_files_only=True)
                except Exception:  # noqa: BLE001 - not downloaded yet
                    self._model = SentenceTransformer(EMBED_MODEL, device="cpu")
            return self._model

    @property
    def ready(self) -> bool:
        return self._model is not None

    def _bm25_rank(self, query: str, n: int) -> list[int]:
        toks = bm25s.tokenize([query], stopwords="en", show_progress=False)
        res, scores = self.bm25.retrieve(toks, k=min(n, len(self.docs)), show_progress=False)
        return [int(i) for i, s in zip(res[0], scores[0]) if s > 0]

    def _dense_ranks(self, queries: list[str], n: int) -> list[list[int]]:
        """One batched encode for all queries (one call per query was ~5x slower on CPU)."""
        prefix = "query: " if "e5" in EMBED_MODEL else ""
        qv = self.model.encode([prefix + q for q in queries], normalize_embeddings=True)
        out = []
        for sims in qv @ self.emb.T:
            top = np.argpartition(-sims, n)[:n]
            out.append([int(i) for i in top[np.argsort(-sims[top])]])
        return out

    def warm_up(self) -> None:
        """Load the embedding model now instead of on the first query (~40 s on CPU)."""
        self._dense_ranks(["warm up"], 1)

    def search(self, query: str, top_k: int = 10, mode: str = "hybrid",
               rerank: bool = False, extra_queries: list[str] | None = None,
               pool: int = 50) -> list[dict]:
        """mode: bm25 | dense | hybrid. extra_queries (e.g. original-language text) are
        embedded too and fused as additional rankings."""
        queries = [query, *(extra_queries or [])]
        rankings: list[list[int]] = []
        if mode in ("bm25", "hybrid"):
            rankings += [self._bm25_rank(q, pool * 2) for q in queries]
        if mode in ("dense", "hybrid"):
            rankings += self._dense_ranks(queries, pool * 2)
        fused = sorted(rrf(rankings).items(), key=lambda kv: -kv[1])[:pool]
        hits = [dict(self.docs[i], score=s, _idx=i) for i, s in fused]
        if rerank and hits:
            hits = self._rerank(query, hits)
        return hits[:top_k]

    def _rerank(self, query: str, hits: list[dict]) -> list[dict]:
        if self._reranker is None:
            from sentence_transformers import CrossEncoder
            self._reranker = CrossEncoder(RERANK_MODEL, device="cpu", max_length=256)
        pairs = [(query, f"{h['is_number']}: {h['title']}") for h in hits]
        scores = self._reranker.predict(pairs, batch_size=16)
        for h, s in zip(hits, scores):
            h["score"] = float(s)
        return sorted(hits, key=lambda h: -h["score"])
