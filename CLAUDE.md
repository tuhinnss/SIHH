# SpecSure (SIH26108, Team "Ding Ding") — agent guide

Recommends applicable Indian Standards for procurement specs; Tender Linter for tender PDFs.
**Read `docs/HANDOFF.md` first** for current state, decisions, gotchas and the prioritised to-do list.

## Hard rules (never break)
1. NEVER write an IS number, title, year or certification rule from memory. Every IS number comes from
   downloaded data (`data/catalogue.jsonl`, `data/refs_extracted.jsonl`, `data/certification.csv`).
   Missing data → show "unknown". (IS numbers in tests/fixtures are test inputs only.)
2. The LLM may only choose from retrieval candidates (JSON schema `is_number` enum), then
   `app/validator.py` re-checks against the catalogue and drops+logs the rest.
3. BIS owns copyright on standard texts: no PDFs/full texts in git. Only metadata, ≤800-char scope
   snippets, reference links. Raw downloads → `data/raw/` (git-ignored); OCR text is processed in memory
   and discarded.
4. Be polite to external sites: 1 request/second, cache, exponential backoff (`data_pipeline/common.py`).
5. Free stack. Keys only via `.env` / environment (`GEMINI_API_KEY`, `GROQ_API_KEY`); never commit or print them.
6. Do not fill `data/certification.csv` yourself — the user fills it by hand from bis.gov.in.

## Commands (run from `backend/`; scripts are modules: `python -m ...`)
```bash
pip install -r requirements.txt        # CPU torch: pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m pytest tests                 # 61 tests, LLM stubbed
python -m data_pipeline.fetch_catalogue    # ~2 min -> data/catalogue.jsonl + data/specsure.sqlite (WIPES edges/snippets)
python -m data_pipeline.build_edges        # re-run after fetch_catalogue (reads data/refs_extracted.jsonl)
python -m data_pipeline.build_index        # ~15 min first time; later runs re-embed only changed docs
uvicorn app.main:app --port 8000
cd ../frontend && npm install && npm run dev   # :5173, proxies /api -> :8000
python -m eval.run_eval                    # needs gold_is filled in eval/eval_set.jsonl
python -m data_pipeline.check_certification
```
Data (`data/specsure.sqlite`, `data/indexes/`) is NOT in git; a fresh clone must rebuild in the order above
(`fetch_catalogue` → `build_edges` → `build_index`). `refs_extracted.jsonl` and `subset_ids.json` ARE committed,
so `extract_refs` (20–60 min) is only needed to grow the subset.

## Layout
`backend/app` (FastAPI: retrieval, recommender, llm, validator, linter, graph, tender, citations, lang) ·
`backend/data_pipeline` (fetch/parse/extract/build scripts) · `backend/eval` · `backend/tests` ·
`frontend/src` (Search, TenderCheck, StandardDetail graph, About) · `docs/` (screenshots, synthetic sample tender).

## Working style
Inspect a real sample before writing any parser. Keep changes minimal; add a pytest for parsers/validators.
Verify UI changes with a real screenshot (Playwright + `/opt/pw-browsers/chromium` in the cloud sandbox).
