import sys
import threading
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.retrieval import Retriever  # noqa: E402


class FakeModel:
    """Encodes 'a'/'b'/'c' as unit vectors along x/y/z; counts encode calls."""
    calls = 0

    def encode(self, texts, normalize_embeddings=True):
        FakeModel.calls += 1
        axes = {"a": 0, "b": 1, "c": 2}
        v = np.zeros((len(texts), 3), dtype="float32")
        for i, t in enumerate(texts):
            v[i, axes[t[-1]]] = 1.0
        return v


def fake_retriever():
    r = Retriever.__new__(Retriever)
    r.emb = np.array([[1, 0, 0], [0.8, 0.6, 0], [0, 1, 0], [0, 0, 1]], dtype="float32")
    r._model, r._reranker, r._lock = FakeModel(), None, threading.Lock()
    return r


def test_dense_ranks_batches_queries_and_ranks_each():
    r = fake_retriever()
    FakeModel.calls = 0
    ranks = r._dense_ranks(["query a", "query b"], 2)
    assert ranks == [[0, 1], [2, 1]]
    assert FakeModel.calls == 1  # one encode for all queries
