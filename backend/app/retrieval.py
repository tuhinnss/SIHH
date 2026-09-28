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
        self.docs: list[dict] = json.loads((INDEX_DIR / "docs.json").read_text())
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
                self._model = SentenceTransformer(EMBED_MODEL, device="cpu")
            return self._model

    def _bm25_rank(self, query: str, n: int) -> list[int]:
        toks = bm25s.tokenize([query], stopwords="en", show_progress=False)
        res, scores = self.bm25.retrieve(toks, k=min(n, len(self.docs)), show_progress=False)
        return [int(i) for i, s in zip(res[0], scores[0]) if s > 0]

    def _dense_rank(self, query: str, n: int) -> list[int]:
        prefix = "query: " if "e5" in EMBED_MODEL else ""
        q = self.model.encode([prefix + query], normalize_embeddings=True)[0]
        sims = self.emb @ q
        top = np.argpartition(-sims, n)[:n]
        return [int(i) for i in top[np.argsort(-sims[top])]]

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
            rankings += [self._dense_rank(q, pool * 2) for q in queries]
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
