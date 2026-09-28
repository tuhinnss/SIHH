import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
DB_PATH = DATA / "specsure.sqlite"
INDEX_DIR = DATA / "indexes"
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-m3")  # fallback: intfloat/multilingual-e5-small
RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
