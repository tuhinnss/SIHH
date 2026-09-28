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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
# Model ids are configurable; verify current free-tier names in each provider's docs.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
INVENTED_LOG = DATA / "invented_is_log.jsonl"
