# SpecSure — handoff for the next agent

Written at the end of the cloud session that built Phases 1–5 (last commit at time of writing: `136961c`),
updated after session 2 (2026-09-30, the user's local Windows machine; branch `local-setup`).
Product: SIH 2026 problem SIH26108 (Ministry of Consumer Affairs / BIS) — recommend applicable Indian
Standards for procurement specs; lint tenders. Read `CLAUDE.md` for the hard rules.

**Session 2 changes:** Windows port (explicit UTF-8 everywhere), `fetch_catalogue` builds from the committed
snapshot (`--refresh` to re-download), LLM reason grounding (to-do #5), Tender Check paging beyond 40 items and a
warning for scanned pages, `extract_refs --retry-failed`, GitHub Actions CI, `eval.from_tenders` (eval rows from
real tender PDFs) and a misses list in `run_eval`. Two bugs found while verifying: the Vite proxy failed on Windows
(every `/api` call 502), and IS 1786 had fallen out of the "TMT steel bars" candidate pool (BM25 length penalty on docs
with scope snippets; BM25 is now title-only). All §5 sanity checks pass on the local machine.

**Session 2, speed pass** (measured with keys on the local 12-core CPU):
| | before | after |
|---|---|---|
| first search after startup | ~50 s (model loaded lazily) | ~4.6 s (warm-up thread at startup; model ready ~13 s after launch) |
| a search | ~7.3 s (retrieval 1.6 s + 2 LLM calls) | ~4–6 s (retrieval 0.2 s: one batched encode) |
| repeated search | ~7 s | ~0.003 s (LRU cache, 256 queries) |
| sample tender, 6 items | 12 LLM calls, ~50 s | 3 calls, ~13–15 s (same primaries, same 1 red + 4 amber) |
| 40-item tender page | 80 calls (~4–5 min, rate-limit risk) | 10 calls, ~75 s, all 40 AI-ranked |
Gemini latency varies a lot (the same batched sample tender once took 49 s); the client retries 5xx silently.

## 1. Where things stand
All five planned phases are built and were verified in a real browser and against live Gemini/Groq:

| Area | State |
|---|---|
| Catalogue | 22,025 records from Internet Archive `gov.in.is.*` → 19,700 searchable standards (latest edition per key). Older snapshot (only ~3,200 records from 2015+). |
| Retrieval | BM25 (bm25s) over `IS number: title` + bge-m3 dense over title (+ scope snippet), RRF fusion, top-50 pool, optional bge-reranker (off by default; did not help on TMT test) |
| LLM | Query expansion/translation → enum-constrained selection → validator → reason grounding → clause built from catalogue fields. Gemini → Groq failover, 60 s cooldown on HTTP 429. Falls back to retrieval-only (`X-LLM-Used: false`). Results are LRU-cached (fallbacks are not, while an LLM is configured). Tenders use `recommend_many`: 1 expansion call per 20 items + 1 selection call per 5 items (30 candidates each), validated per item |
| Relations | 298/300 subset standards extracted (steel/cement, cables/electrical, pipes/plumbing) → 1,300 edges (909 normative_ref, 195 test_method, 47 terminology, 65 scope_ref, 84 supersedes); 248 scope snippets. 81% of extracted refs resolve to the catalogue. `same_series` is derived at query time. |
| Tender Check | PyMuPDF → line items (numbered/BOQ/bullets; LLM split only if <2 items) → recommend per item (40 per request; `?offset=` + "Analyse items 41–80" button for more) → linter (superseded🔴, no_certification🔴, not_in_catalogue🟠, older_edition🟠, brand_name🟠) → printable audit report. Image-only (scanned) pages are counted and reported in `warning`; no OCR |
| Frontend | React+Vite+Tailwind: Search, Tender Check, Standard (react-force-graph-2d), About |
| Tests | 78 pytest tests (parsers, citations incl. strip_citations, eval row harvesting, index texts, batched dense ranking, validator, reason grounding, recommender with stub LLM incl. cache and tender batching, linter, tender/PDF incl. paging and scans, certification check, metrics); CI runs them plus the frontend build (`.github/workflows/ci.yml`) |
| Eval | `backend/eval` harness works (BM25/dense/hybrid/hybrid+rerank+LLM; invented-IS count must be 0) but `eval_set.jsonl` has **no gold rows** → no accuracy numbers exist yet |
| Certification | `data/certification.csv` is an empty template on purpose |

## 2. Prioritised to-do (highest value first)
1. **Real evaluation.** Ask the user for (or help them collect) 30–100 real GeM/CPPP tender lines with the IS
   numbers they cite. Easiest path: real tender PDFs → `python -m eval.from_tenders *.pdf` (query = item text minus
   citations, gold = what the tender cited) → user reviews `eval/tender_rows.jsonl` → `python -m eval.run_eval --file
   eval/tender_rows.jsonl`, which also lists the full pipeline's misses. Or fill `backend/eval/eval_set.jsonl` by hand;
   analyse failures by category (abbreviation gaps like "TMT", multi-part standards, Hindi). Never invent gold rows.
2. **Certification table** — the user fills `data/certification.csv` by hand; you only run
   `python -m data_pipeline.check_certification` and verify the badge/`no_certification` flag end to end
   (currently only unit-tested with fake rows).
3. **Grow relation coverage** beyond the 300-standard subset: edit `VERTICALS`/`PER_VERTICAL` in
   `data_pipeline/select_subset.py` (or add verticals), rerun `extract_refs` (resumable; ~3–20 s/standard at 1 req/s),
   then `build_edges` and `build_index`. Ask the user which procurement categories matter for the demo first
   (naive title regexes are noisy: "fans" matches fuel-pump titles). Two standards (`gov.in.is.9550.2001`,
   `gov.in.is.17482.2020`) fail because archive.org answers HTTP 500 for their OCR files (re-checked 2026-09-30);
   retry later with `extract_refs --retry-failed`.
4. **Retrieval quality:** try adding scope snippets for more standards, query-side abbreviations via the LLM
   expansion (already helps), tune RRF/pool sizes against the eval set, re-test `RERANK` with real gold data.
5. ~~LLM reason grounding~~ — done: `validator.ground_reason` drops a reason whose numbers or certification terms
   are not in the candidate line (`IS number (year): title`, all the LLM sees) or the requirement. Wording-level
   over-claims without numbers can still slip through.
6. **Tender robustness:** scanned pages are now detected and reported, but not read — OCR still needs a decision
   (Tesseract via PyMuPDF `get_textpage_ocr` needs a system install; RapidOCR is pip-only). Test on real tender PDFs;
   consider IndicTrans2 for Hindi (currently the LLM translates).
7. Nice-to-have: Docker/compose, frontend tests. (CI and Tender Check paging are done.)

## 3. Decisions and gotchas learned the hard way
* **Archive API:** `advancedsearch` caps deep paging at 10,000 → use the Scraping API (`fetch_raw.py`). Downloads under
  `/download/{id}/{file}` return a 302 to another archive host — the HTTP client must follow redirects. File names contain
  `:` (e.g. `IS4985:2021_djvu.txt`); `extract_refs` URL-quotes them. Amendment files start with `z…` and are skipped.
* **Identifier is the source of truth for parsing** (`gov.in.is.[family.][joint.]num[.part[.sec]][.flag].year`); the
  archive `date` field is an upload date, not the edition year. Titles had mojibake (repaired in `parsing.fix_mojibake`).
* **Keys:** `IS-{num}[-P{part}][-S{sec}]`, joint prefix kept (`IS-ISO-IEC-17799`), year ignored. One retrieval doc per key
  (latest edition, English copy preferred); older editions stay in SQLite for version checks.
* **Reference lists are OCR'd in columns** (bare numbers like `4905 : 2015/`, `12235` then `(Part 1) : 2004`) or as inline
  rows under `REFERENCES`/`NORMATIVE REFERENCES`; page numbers and year-only lines must be ignored (`refs_parsing.py`).
* **Citation resolution** (`CatalogueIndex.resolve`): exact key first; joint-prefix-ignoring fallback ONLY for numbers with
  ≥5 digits (a plain "IS 691" must not match "IS/IEC 691"). Supersedes edges use exact matching only.
* **Foreword-derived supersession is noisy:** negated mentions are skipped, and a resolved target must share a subject word
  with the new standard's title (`build_edges.plausible`). Title-derived "(Superseding IS x)" edges are trusted.
* **The LLM sees the whole top-50 pool** (not just top_k), and standards cited in the requirement text are added to the
  candidates. Earlier versions passed only top_k and missed IS 1786.
* **BM25 must not see scope snippets.** Appending ~800-char snippets to ~250 docs made them ~20x longer than the title-only
  majority; BM25 length normalisation then buried exactly those key standards (IS 1786 fused rank 55 for "TMT steel bars"
  with Gemini's expansion → outside the pool). `build_index.bm25_text` is number + title; `doc_text` (dense) adds the
  snippet. With 1 query + 6 expansion terms RRF fuses 14 lists, so a doc strong in only 2 lists is easily diluted —
  worth tuning (k, per-list weights) once real gold data exists.
* **Batched selection enum = union of the batch's candidates**, so the schema alone cannot stop an item picking another
  item's standard; `Recommender._cards` validates each item against its OWN candidates (tested). Keep that if you
  change batching. Selection batches run sequentially on purpose: parallel calls would likely trip free-tier rate
  limits (untested), and a 429 on Gemini fails over to Groq, whose token limit is small for ~14k-char batch prompts.
* **Model load:** `Retriever.model` tries `local_files_only=True` first (skips a ~10 s Hugging Face online check);
  importing torch/transformers alone takes 12–22 s on this Windows machine.
* **Frontend proxy targets `127.0.0.1:8000`, not `localhost`:** Node 17+ resolves localhost to `::1` first, uvicorn
  listens on IPv4 only → `ECONNREFUSED ::1:8000` and 502 on every `/api` call (seen on Windows).
* **LLM models:** defaults `gemini-flash-lite-latest` and Groq `openai/gpt-oss-120b`; both overridable
  (`GEMINI_MODEL`, `GROQ_MODEL`). `gemini-2.5-flash` and `llama-3.3-70b-versatile` no longer exist for these keys; the
  `-latest` alias on the full Flash model exhausts the free quota fast; `gpt-oss-20b` chose worse standards. Re-check the
  providers' model lists if calls start failing with 404.
* **Embeddings:** `build_index` re-embeds only docs whose text hash changed (hashes in `data/indexes/meta.json`). Changing
  `EMBED_MODEL` invalidates everything.
* **`fetch_catalogue` deletes and recreates the SQLite DB** (edges + scope snippets vanish) → always re-run `build_edges`.
* Sandbox-only note: `pkill -f`/`pgrep -f` inside a command that also contains the pattern kills its own shell; use pid files.
* **Windows (session 2):** `open()`/`read_text()` default to cp1252 → always pass `encoding="utf-8"`. The MSYS2 `python`
  first on PATH cannot install torch; the venv uses python.org 3.12 (`backend/.venv`). git has `core.autocrlf=true`, so
  source files are CRLF in the working tree. The Hugging Face cache warns about symlinks (harmless). On this
  machine the first `build_index` took ~10 min to download bge-m3 (2.3 GB, hf-xet) and 64 min to embed 19,700 docs on
  12 CPU cores (later runs re-embed only changed docs: seconds). The console is cp1252 too: set
  `PYTHONIOENCODING=utf-8` when a script prints Hindi. `run_eval`'s full setup uses `rerank=True`, which downloads
  bge-reranker-v2-m3 (~2 GB) on first use; it has not been downloaded on this machine yet.
* **Agent tooling:** the Bash tool collapses `\\n` inside inline heredoc scripts into a real newline — write Python
  helpers to a file when a string literal must contain `\n`.
* **Keys** go in the git-ignored `.env` (`config.py` loads `ROOT/.env`); keep the tracked `.env.example` blank.

## 4. Key files
`backend/app/recommender.py` (pipeline + prompts) · `retrieval.py` · `llm.py` · `validator.py` · `linter.py` ·
`graph.py` (allied/supersedes/detail) · `catalogue.py` (resolve/version index) · `citations.py` (IS regex) ·
`tender.py`/`analyze.py` (PDF) · `data_pipeline/{parsing,refs_parsing,extract_refs,build_edges,build_index,select_subset}.py`.

## 5. Sanity checks after setting up a new machine
All four passed on the local Windows machine on 2026-09-30 (plus Hindi/Hinglish PVC queries → IS 4985 primary, a
scanned PDF → warning, a 45-item tender → 40 + "Analyse items 41–45").
1. `python -m pytest tests` → 78 passed.
2. `curl -X POST localhost:8000/recommend -H 'content-type: application/json' -d '{"text":"TMT steel bars for RCC"}'` →
   with keys: IS 1786 primary and header `X-LLM-Used: true`; without keys: retrieval-only.
3. Frontend Tender Check with `docs/sample_tender.pdf` → 1 red (IS 445 superseded by IS 444), 4 amber.
4. `/stats` → ~22,025 records, ~1,300 edges.
