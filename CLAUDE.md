# Kalamkaar (SIH26108, Team "Ding Ding") — agent guide

Recommends applicable Indian Standards for procurement specs; Tender Linter for tender PDFs.
**Read `docs/HANDOFF.md` first** for current state, decisions, gotchas and the prioritised to-do list.

## Hard rules (never break)
1. NEVER write an IS number, title, year or certification rule from memory. Every IS number comes from
   downloaded data (`data/catalogue.jsonl`, `data/refs_extracted.jsonl`, `data/certification.csv`).
   Missing data → show "unknown". (IS numbers in tests/fixtures are test inputs only.)
2. The LLM may only choose from retrieval candidates (JSON schema `is_number` enum), then
   `app/validator.py` re-checks against the catalogue and drops+logs the rest, and drops reasons that
   state numbers/certification terms absent from the candidate line and requirement (`ground_reason`).
3. BIS owns copyright on standard texts: no PDFs/full texts in git. Only metadata, ≤800-char scope
   snippets, reference links. Raw downloads → `data/raw/` (git-ignored); OCR text is processed in memory
   and discarded.
4. Be polite to external sites: 1 request/second, cache, exponential backoff (`data_pipeline/common.py`).
5. Free stack. Keys only via `.env` / environment (`GEMINI_API_KEY`, `GROQ_API_KEY`); never commit or print them.
6. Do not fill `data/certification.csv` yourself — the user fills it by hand from bis.gov.in.

## Commands (run from `backend/`; scripts are modules: `python -m ...`)
```bash
pip install -r requirements.txt        # CPU torch: pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m pytest tests                 # 91 tests, LLM stubbed (also run by CI: .github/workflows/ci.yml)
python -m data_pipeline.fetch_catalogue    # ~2 s from committed catalogue.jsonl -> data/kalamkaar.sqlite (WIPES edges/snippets)
                                           # --refresh re-downloads the archive listing (~2 min, rewrites catalogue.jsonl)
python -m data_pipeline.build_edges        # re-run after fetch_catalogue (reads data/refs_extracted.jsonl)
python -m data_pipeline.build_index        # ~15-75 min first time (CPU); later runs re-embed only changed docs
uvicorn app.main:app --port 8000
cd ../frontend && npm install && npm run dev   # :5173, proxies /api -> :8000
python -m eval.from_tenders tenders/*.pdf  # real tenders -> eval/tender_rows.jsonl (gold = cited IS; user reviews)
python -m eval.run_eval [--file ...]       # needs gold rows; lists the full pipeline's misses
python -m data_pipeline.check_certification
```
Data (`data/kalamkaar.sqlite`, `data/indexes/`) is NOT in git; a fresh clone must rebuild in the order above
(`fetch_catalogue` → `build_edges` → `build_index`). `refs_extracted.jsonl` and `subset_ids.json` ARE committed,
so `extract_refs` (20–60 min) is only needed to grow the subset.

Local Windows machine: the venv is `backend/.venv` (python.org Python 3.12; the MSYS2 `python` on PATH
cannot install torch) → run `.venv/Scripts/python.exe -m ...`. Always pass `encoding="utf-8"` to
`open()`/`read_text()`/`write_text()` (Windows defaults to cp1252).

## Layout
`backend/app` (FastAPI: retrieval, recommender, llm, validator, linter, graph, tender, citations, lang) ·
`backend/data_pipeline` (fetch/parse/extract/build scripts) · `backend/eval` · `backend/tests` ·
`frontend/src` (Search, TenderCheck, StandardDetail graph, About) · `docs/` (screenshots, synthetic sample tender).

## Working style
Inspect a real sample before writing any parser. Keep changes minimal; add a pytest for parsers/validators.
Verify UI changes with a real screenshot (Playwright + `/opt/pw-browsers/chromium` in the cloud sandbox).
