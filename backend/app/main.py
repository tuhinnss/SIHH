import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import DB_PATH
from app.retrieval import Retriever

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    state["retriever"] = Retriever()
    yield


app = FastAPI(title="SpecSure API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class RecommendReq(BaseModel):
    text: str
    lang: str | None = None
    top_k: int = 10
    rerank: bool = False


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/recommend")
def recommend(req: RecommendReq):
    hits = state["retriever"].search(req.text, top_k=req.top_k, rerank=req.rerank)
    return [{
        "is_number": h["is_number"], "title": h["title"], "year": h["year"],
        "relevance": "primary", "reason": None, "confidence": round(h["score"], 4),
        "supersedes_info": None, "allied": [], "certification": None,
        "source_url": h["source_url"],
    } for h in hits]


@app.get("/stats")
def stats():
    with sqlite3.connect(DB_PATH) as db:
        n = db.execute("select count(*) from standards").fetchone()[0]
    return {"catalogue_records": n, "retrieval_documents": len(state["retriever"].docs),
            "edges": 0, "last_sync": "see data/raw/ia_docs.jsonl mtime",
            "note": "Archive snapshot is older; verify on BIS Know Your Standards."}
