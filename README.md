# SpecSure — SIH26108 (Team "Ding Ding")

AI-powered recommendation of applicable Indian Standards for procurement specifications.
**Prototype — verify on BIS Know Your Standards.**

## Data & honesty rules
- Every IS number comes from `data/catalogue.jsonl`, built from the Internet Archive
  `gov.in.is.*` collection (22,025 records → 19,700 distinct standards). It is an **older
  snapshot** (only ~3,200 records are from 2015 or later), so "latest version" means
  *as per our catalogue*.
- No standard texts or PDFs are stored in git — metadata only. Raw downloads go to `data/raw/` (git-ignored).
- Certification info shows only for rows hand-filled in `data/certification.csv` (currently empty).

## Phase 1 setup
```bash
cd backend
pip install -r requirements.txt   # CPU torch: pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m data_pipeline.fetch_catalogue   # ~1.5 min, cached; writes data/catalogue.jsonl + data/specsure.sqlite
python -m data_pipeline.build_index       # ~15 min on 4 CPUs (bge-m3); EMBED_MODEL=intfloat/multilingual-e5-small is faster
uvicorn app.main:app --port 8000
cd ../frontend && npm install && npm run dev   # http://localhost:5173
python -m pytest backend/tests
```

## Known Phase 1 limitation
Retrieval is vocabulary-bound: "TMT steel bars" does not surface IS 1786 (its title says
"High strength deformed steel bars…"). LLM query expansion and reranking come in Phase 2.

## Phase 2: LLM selection (Gemini -> Groq fallback)
Flow: LLM expands/translates the query (search terms only, no IS numbers) -> hybrid retrieval
over query + expansions -> LLM picks from the top-50 candidates through a JSON schema whose
`is_number` is an **enum of those candidates** -> every pick is re-validated against the
catalogue; anything else is dropped and logged to `data/invented_is_log.jsonl` -> the copy-ready
clause is built from catalogue fields, never from LLM text. With no keys or on LLM failure the API
returns retrieval-only results (`X-LLM-Used: false`, no reasons).

Keys are read from `.env` or environment variables. `python -m pytest backend/tests` runs with a stub LLM.
**Status:** tested against a stub only; not yet run against live Gemini/Groq.

## Phase 3: Tender Check
`POST /analyze-tender` (PDF, max 20 MB): PyMuPDF text -> line items (numbered lines, BOQ table rows,
bullets; LLM-assisted split only if heuristics find <2 items; first 40 items analysed) ->
`/recommend` logic per item -> Tender Linter:

| Flag | Severity | Rule |
|---|---|---|
| superseded | red | cited IS is the older side of a `supersedes` edge (edges arrive in Phase 4) |
| no_certification | red | `certification.csv` (dated, active rows only) requires a mark but the item has no certification wording |
| not_in_catalogue | amber | cited IS not in our (older) catalogue |
| older_edition | amber | cited year < catalogue's latest year |
| brand_name | amber | pattern-based (®/™, "Make:", "M/s X") and no "or equivalent" |

The UI exports a printable audit report (browser "Save as PDF"). `docs/sample_tender.pdf` is a
synthetic demo input. Limitations: scanned/image-only PDFs need OCR (not included); all-caps text
such as "PRICE IS 100" can look like a citation and will be flagged "not in catalogue".
