"""Build BM25 index over "IS number + title" and dense index over "IS number + title (+ scope snippet)".

One retrieval document per standard key: the latest edition, preferring the plain
English copy over Hindi/bilingual/tentative/supplement copies. Older editions stay in
SQLite (used later by the version checker / Tender Linter).
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from sqlmodel import Session, create_engine, select
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import DB_PATH, EMBED_MODEL, INDEX_DIR  # noqa: E402
from app.models import StandardRow  # noqa: E402


def bm25_text(r: dict) -> str:
    """BM25 sees number + title only. With the scope snippet appended, the ~250 extracted standards
    were ~20x longer than the other title-only docs and BM25 length normalisation buried them
    (IS 1786 fell out of the 50-candidate pool for "TMT steel bars")."""
    return f"{r['is_number']}: {r['title']}"


def doc_text(r: dict) -> str:
    """Dense text: the title plus the scope snippet where one was extracted."""
    text = bm25_text(r)
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
    (INDEX_DIR / "docs.json").write_text(json.dumps(docs, ensure_ascii=False), encoding="utf-8")

    tok = bm25s.tokenize([bm25_text(d) for d in docs], stopwords="en")
    bm = bm25s.BM25()
    bm.index(tok)
    bm.save(str(INDEX_DIR / "bm25"))

    emb_path, meta_path = INDEX_DIR / "emb.npy", INDEX_DIR / "meta.json"
    hashes = [hashlib.md5(t.encode()).hexdigest() for t in texts]
    old_vecs, old_by_hash = None, {}
    if emb_path.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("model") == EMBED_MODEL and meta.get("hashes"):
            old_vecs = np.load(emb_path)
            old_by_hash = {h: i for i, h in enumerate(meta["hashes"])}
    model = None
    dim = old_vecs.shape[1] if old_vecs is not None else None
    todo = [i for i, h in enumerate(hashes) if h not in old_by_hash]
    print(f"{len(texts) - len(todo)} embeddings reused, {len(todo)} to compute")
    if todo:
        model = SentenceTransformer(EMBED_MODEL, device="cpu")
        model.max_seq_length = 128
        dim = model.get_sentence_embedding_dimension()
    out = np.zeros((len(texts), dim or 1), dtype="float32")
    for i, h in enumerate(hashes):
        if h in old_by_hash:
            out[i] = old_vecs[old_by_hash[h]]
    prefix = passage_prefix(EMBED_MODEL)
    todo.sort(key=lambda j: len(texts[j]))  # length-sorted batches; restored by index
    bs = 64
    for i in tqdm(range(0, len(todo), bs), desc="embedding", disable=not todo):
        idx = todo[i:i + bs]
        out[idx] = model.encode([prefix + texts[j] for j in idx], normalize_embeddings=True, batch_size=bs)
    np.save(emb_path, out)
    meta_path.write_text(json.dumps({"model": EMBED_MODEL, "n": len(texts), "hashes": hashes}), encoding="utf-8")


if __name__ == "__main__":
    main()
