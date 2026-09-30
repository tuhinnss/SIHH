# SpecSure — handoff for the next agent

Written at the end of the cloud session that built Phases 1–5 (last commit at time of writing: `136961c`).
Product: SIH 2026 problem SIH26108 (Ministry of Consumer Affairs / BIS) — recommend applicable Indian
Standards for procurement specs; lint tenders. Read `CLAUDE.md` for the hard rules.

## 1. Where things stand
All five planned phases are built and were verified in a real browser and against live Gemini/Groq:

| Area | State |
|---|---|
| Catalogue | 22,025 records from Internet Archive `gov.in.is.*` → 19,700 searchable standards (latest edition per key). Older snapshot (only ~3,200 records from 2015+). |
| Retrieval | BM25 (bm25s) + bge-m3 dense, RRF fusion, top-50 pool, optional bge-reranker (off by default; did not help on TMT test) |
| LLM | Query expansion/translation → enum-constrained selection → validator → clause built from catalogue fields. Gemini → Groq failover, 60 s cooldown on HTTP 429. Falls back to retrieval-only (`X-LLM-Used: false`) |
| Relations | 298/300 subset standards extracted (steel/cement, cables/electrical, pipes/plumbing) → 1,300 edges (909 normative_ref, 195 test_method, 47 terminology, 65 scope_ref, 84 supersedes); 248 scope snippets. 81% of extracted refs resolve to the catalogue. `same_series` is derived at query time. |
| Tender Check | PyMuPDF → line items (numbered/BOQ/bullets; LLM split only if <2 items) → recommend per item (max 40) → linter (superseded🔴, no_certification🔴, not_in_catalogue🟠, older_edition🟠, brand_name🟠) → printable audit report |
| Frontend | React+Vite+Tailwind: Search, Tender Check, Standard (react-force-graph-2d), About |
| Tests | 61 pytest tests (parsers, citations, validator, recommender with stub LLM, linter, tender/PDF, certification check, metrics) |
| Eval | `backend/eval` harness works (BM25/dense/hybrid/hybrid+rerank+LLM; invented-IS count must be 0) but `eval_set.jsonl` has **no gold rows** → no accuracy numbers exist yet |
| Certification | `data/certification.csv` is an empty template on purpose |

## 2. Prioritised to-do (highest value first)
1. **Real evaluation.** Ask the user for (or help them collect) 30–100 real GeM/CPPP tender lines with the IS
   numbers they cite; fill `backend/eval/eval_set.jsonl` (`{query, gold_is:[...], lang}`); run `python -m eval.run_eval`;
   analyse failures by category (abbreviation gaps like "TMT", multi-part standards, Hindi). Never invent gold rows.
2. **Certification table** — the user fills `data/certification.csv` by hand; you only run
   `python -m data_pipeline.check_certification` and verify the badge/`no_certification` flag end to end
   (currently only unit-tested with fake rows).
3. **Grow relation coverage** beyond the 300-standard subset: edit `VERTICALS`/`PER_VERTICAL` in
   `data_pipeline/select_subset.py` (or add verticals), rerun `extract_refs` (resumable; ~3–20 s/standard at 1 req/s),
   then `build_edges` and `build_index`. Two standards keep returning HTTP errors on download — retry later.
4. **Retrieval quality:** try adding scope snippets for more standards, query-side abbreviations via the LLM
   expansion (already helps), tune RRF/pool sizes against the eval set, re-test `RERANK` with real gold data.
5. **LLM reason grounding:** small models sometimes over-claim in the one-line reason. Options: shorten reasons to
   title-derived phrases, add a cheap grounding check, or drop reason text when it mentions facts not in the title.
6. **Tender robustness:** scanned/image PDFs need OCR (not implemented); test on real tender PDFs; consider
   IndicTrans2 for Hindi (currently the LLM translates).
7. Nice-to-have: Docker/compose, CI running pytest, frontend tests, pagination in Tender Check for >40 items.

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
* **LLM models:** defaults `gemini-flash-lite-latest` and Groq `openai/gpt-oss-120b`; both overridable
  (`GEMINI_MODEL`, `GROQ_MODEL`). `gemini-2.5-flash` and `llama-3.3-70b-versatile` no longer exist for these keys; the
  `-latest` alias on the full Flash model exhausts the free quota fast; `gpt-oss-20b` chose worse standards. Re-check the
  providers' model lists if calls start failing with 404.
* **Embeddings:** `build_index` re-embeds only docs whose text hash changed (hashes in `data/indexes/meta.json`). Changing
  `EMBED_MODEL` invalidates everything.
* **`fetch_catalogue` deletes and recreates the SQLite DB** (edges + scope snippets vanish) → always re-run `build_edges`.
* Sandbox-only note: `pkill -f`/`pgrep -f` inside a command that also contains the pattern kills its own shell; use pid files.

## 4. Key files
`backend/app/recommender.py` (pipeline + prompts) · `retrieval.py` · `llm.py` · `validator.py` · `linter.py` ·
`graph.py` (allied/supersedes/detail) · `catalogue.py` (resolve/version index) · `citations.py` (IS regex) ·
`tender.py`/`analyze.py` (PDF) · `data_pipeline/{parsing,refs_parsing,extract_refs,build_edges,build_index,select_subset}.py`.

## 5. Sanity checks after setting up a new machine
1. `python -m pytest tests` → 61 passed.
2. `curl -X POST localhost:8000/recommend -H 'content-type: application/json' -d '{"text":"TMT steel bars for RCC"}'` →
   with keys: IS 1786 primary and header `X-LLM-Used: true`; without keys: retrieval-only.
3. Frontend Tender Check with `docs/sample_tender.pdf` → 1 red (IS 445 superseded by IS 444), 4 amber.
4. `/stats` → ~22,025 records, ~1,300 edges.
