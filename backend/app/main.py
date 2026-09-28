import sqlite3
from datetime import date
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import DATA as DATA_DIR, DB_PATH
from app.analyze import analyze_pdf
from app.catalogue import CatalogueIndex
from app.certification import CertificationTable
from app.graph import Graph
from app.linter import Linter
from app.llm import LLMClient
from app.recommender import Recommender
from app.retrieval import Retriever

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    retriever = Retriever()
    state["retriever"] = retriever
    cert = CertificationTable.load()
    cat = CatalogueIndex.from_sqlite()
    graph = Graph.from_sqlite(cat)
    state["graph"] = graph
    state["recommender"] = Recommender(
        retriever, LLMClient.from_env(), {d["is_number"]: d for d in retriever.docs}, cert=cert,
        graph=graph)
    state["linter"] = Linter(cat, cert)
    yield


app = FastAPI(title="SpecSure API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["X-LLM-Used", "X-Detected-Lang", "X-English-Query"])


class RecommendReq(BaseModel):
    text: str
    lang: str | None = None
    top_k: int = 10
    rerank: bool = False


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/recommend")
def recommend(req: RecommendReq, response: Response):
    out = state["recommender"].recommend(req.text, top_k=req.top_k, rerank=req.rerank, lang=req.lang)
    response.headers["X-LLM-Used"] = str(out["llm_used"]).lower()
    response.headers["X-Detected-Lang"] = out["lang"]
    response.headers["X-English-Query"] = out["english_query"].encode("ascii", "ignore").decode()[:200]
    return out["results"]


@app.post("/analyze-tender")
async def analyze_tender(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, "PDF too large (max 20 MB)")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "Please upload a PDF file")
    try:
        return analyze_pdf(data, file.filename or "tender.pdf", state["recommender"], state["linter"])
    except Exception as e:  # noqa: BLE001 - corrupt/encrypted PDFs etc.
        raise HTTPException(422, f"Could not read this PDF ({type(e).__name__})")


@app.get("/standard/{is_number:path}")
def standard(is_number: str):
    g = state["graph"]
    key = g.find_key(is_number)
    if not key:
        raise HTTPException(404, f"'{is_number}' is not in our catalogue (older archive snapshot). "
                                 "Verify on BIS Know Your Standards.")
    return g.detail(key)


@app.get("/stats")
def stats():
    with sqlite3.connect(DB_PATH) as db:
        n = db.execute("select count(*) from standards").fetchone()[0]
        by_type = dict(db.execute("select edge_type,count(*) from edges group by edge_type").fetchall())
        scoped = db.execute("select count(*) from standards where scope_snippet is not null").fetchone()[0]
    ia = DATA_DIR / "raw" / "ia_docs.jsonl"
    synced = date.fromtimestamp(ia.stat().st_mtime).isoformat() if ia.exists() else None
    return {"catalogue_records": n, "retrieval_documents": len(state["retriever"].docs),
            "edges": sum(by_type.values()), "edges_by_type": by_type,
            "standards_with_scope_text": scoped, "last_sync": synced,
            "certification_rows": len(state["recommender"].cert.rows) if state["recommender"].cert else 0,
            "note": "Archive snapshot is older; verify on BIS Know Your Standards."}
