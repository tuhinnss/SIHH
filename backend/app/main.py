import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import DB_PATH
from app.analyze import analyze_pdf
from app.catalogue import CatalogueIndex
from app.certification import CertificationTable
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
    state["recommender"] = Recommender(
        retriever, LLMClient.from_env(), {d["is_number"]: d for d in retriever.docs}, cert=cert)
    state["linter"] = Linter(CatalogueIndex.from_sqlite(), cert)
    yield


app = FastAPI(title="SpecSure API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["X-LLM-Used"])


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
    out = state["recommender"].recommend(req.text, top_k=req.top_k, rerank=req.rerank)
    response.headers["X-LLM-Used"] = str(out["llm_used"]).lower()
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


@app.get("/stats")
def stats():
    with sqlite3.connect(DB_PATH) as db:
        n = db.execute("select count(*) from standards").fetchone()[0]
    return {"catalogue_records": n, "retrieval_documents": len(state["retriever"].docs),
            "edges": 0, "last_sync": "see data/raw/ia_docs.jsonl mtime",
            "note": "Archive snapshot is older; verify on BIS Know Your Standards."}
