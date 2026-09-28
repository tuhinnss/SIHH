"""Build BM25 + dense index over "IS number + title (+ scope snippet)".

One retrieval document per standard key: the latest edition, preferring the plain
English copy over Hindi/bilingual/tentative/supplement copies. Older editions stay in
SQLite (used later by the version checker / Tender Linter).
"""
import json
import sys
from pathlib import Path

import numpy as np
from sqlmodel import Session, create_engine, select
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import DB_PATH, EMBED_MODEL, INDEX_DIR  # noqa: E402
from app.models import StandardRow  # noqa: E402


def doc_text(r: dict) -> str:
    text = f"{r['is_number']}: {r['title']}"
    if r.get("scope_snippet"):
        text += f". {r['scope_snippet']}"
    return text


def passage_prefix(model: str) -> str:
    return "passage: " if "e5" in model else ""


def load_docs() -> list[dict]:
    engine = create_engine(f"sqlite:///{DB_PATH}")
    with Session(engine) as s:
        rows = [r.model_dump() for r in s.exec(select(StandardRow))]
    best: dict[str, dict] = {}
    for r in rows:
        rank = (r["year"] or 0, not r["flags"])  # newest edition, then plain copy
        cur = best.get(r["key"])
        if cur is None or rank > (cur["year"] or 0, not cur["flags"]):
            best[r["key"]] = r
    return sorted(best.values(), key=lambda r: r["key"])


def main() -> None:
    import bm25s
    from sentence_transformers import SentenceTransformer

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    docs = load_docs()
    texts = [doc_text(d) for d in docs]
    print(f"{len(docs)} retrieval documents")
    (INDEX_DIR / "docs.json").write_text(json.dumps(docs, ensure_ascii=False))

    tok = bm25s.tokenize(texts, stopwords="en")
    bm = bm25s.BM25()
    bm.index(tok)
    bm.save(str(INDEX_DIR / "bm25"))

    emb_path = INDEX_DIR / "emb.npy"
    if emb_path.exists() and json.loads((INDEX_DIR / "meta.json").read_text()).get("model") == EMBED_MODEL:
        print("embeddings cached, skipping")
        return
    model = SentenceTransformer(EMBED_MODEL, device="cpu")
    model.max_seq_length = 128
    prefix = passage_prefix(EMBED_MODEL)
    # sort by length so batches are dense; restore order afterwards
    order = np.argsort([len(t) for t in texts])
    out = np.zeros((len(texts), model.get_sentence_embedding_dimension()), dtype="float32")
    bs = 64
    for i in tqdm(range(0, len(texts), bs), desc="embedding"):
        idx = order[i:i + bs]
        out[idx] = model.encode([prefix + texts[j] for j in idx], normalize_embeddings=True,
                                batch_size=bs)
    np.save(emb_path, out)
    (INDEX_DIR / "meta.json").write_text(json.dumps({"model": EMBED_MODEL, "n": len(texts)}))


if __name__ == "__main__":
    main()
