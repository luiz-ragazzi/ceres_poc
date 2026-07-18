# Compliance Intelligence Platform (POC)

A full-stack app to upload pharmaceutical regulatory/compliance PDFs (FDA 21
CFR, EMA Annexes, ICH guidelines, internal SOPs), chunk them by **regulatory
structure** rather than fixed token size, and run semantic search and
grounded Q&A against them — fully on-premises, with every answer traceable
back to Authority → Regulation → Section → Paragraph.

## Project Structure

```
compliance-assistant-poc/
├── Backend (Python modules with separation of concerns)
│   ├── main.py                  ← FastAPI application entry point
│   ├── config.py                ← Configuration, authority/keyword tables
│   ├── database.py              ← ChromaDB operations (filterable queries)
│   ├── embedder.py              ← Embedding model handling
│   ├── models.py                ← Data models (request/response schemas)
│   ├── pdf_processor.py         ← PDF -> Markdown (Docling) + page lookup
│   ├── regulatory_parser.py     ← Part/Subpart/Section/Paragraph chunker
│   ├── regulatory_metadata.py   ← Mandatory compliance metadata schema
│   ├── test_regulatory_parser.py← Unit tests for the parser
│   └── requirements.txt         ← Python dependencies
│
├── Frontend (React + Vite)
│   ├── src/
│   │   ├── App.jsx          ← React UI component
│   │   ├── main.jsx         ← Application entry
│   │   └── assets/
│   ├── public/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── eslint.config.js
│
└── chroma_db/               ← Vector database storage (persisted locally)
```

---

## Backend Module Architecture

The backend follows a **separation of concerns** pattern with each module handling a specific responsibility:

| Module | Responsibility |
|---|---|
| `main.py` | FastAPI application, route definitions, request/response handling |
| `config.py` | Configuration constants, authority/GxP/topic keyword tables |
| `database.py` | ChromaDB operations, `where`-filtered compliance queries |
| `embedder.py` | Embedding model initialization and inference |
| `models.py` | Data models and schemas (Pydantic models, type definitions) |
| `pdf_processor.py` | PDF → Markdown (Docling) and PDF-page lookup per chunk |
| `regulatory_parser.py` | Part/Subpart/Section/Paragraph structure extraction and requirement-level chunking |
| `regulatory_metadata.py` | Mandatory `ChunkMetadata` / `Citation` schema |

---

## Chunking Architecture: Generic Token Splitting -> Regulatory Structure

**Before:** documents were split by heading (via Docling's `HybridChunker`),
token-bounded to the embedding model's context window, with no concept of
regulatory hierarchy — a chunk could span multiple obligations, or split one
obligation across chunks arbitrarily.

**Now:**

```
PDF
 -> Docling (layout-aware PDF -> Markdown, preserves heading tree)
 -> regulatory_parser.extract_regulation_structure()
      -> identify_parts() / identify_subparts() / identify_sections()
 -> regulatory_parser.identify_paragraphs()
      -> one chunk per lettered/numbered obligation, e.g. §11.10(e)
 -> oversized-paragraph splitter (sequence-numbered, metadata preserved)
 -> regulatory_metadata.ChunkMetadata enrichment (authority, gxp_area, ...)
 -> embeddings (sentence-transformers, on-prem)
 -> ChromaDB (metadata flattened via ChunkMetadata.to_chroma_metadata())
```

Every chunk carries the full mandatory metadata schema (`chunk_id`,
`document_id`, `authority`, `regulation`, `part`, `subpart`, `section`,
`paragraph`, `topic`, `gxp_area`, `compliance_domain`, `chunk_type`,
`citation`, ...) with unresolved fields set to `"unknown"` rather than
omitted, so `where` filters and audit exports never have to special-case a
missing key. See `regulatory_metadata.py` for the full schema and
`regulatory_parser.py`'s module docstring for the two document shapes it
handles (CFR-style §-numbered regulations and numbered guidance headings).

### Why this matters

| Dimension | Generic chunking | Regulatory structure-based chunking |
|---|---|---|
| **Compliance** | A chunk may mix unrelated obligations, weakening any single citation | One chunk = one obligation; every retrieved chunk is a specific, defensible requirement |
| **Traceability** | Only a heading path string, no structured Authority/Part/Section/Paragraph | Full `Authority -> Regulation -> Part -> Subpart -> Section -> Paragraph` on every chunk |
| **Auditability** | Reconstructing "what did the model cite" requires re-reading surrounding text | `citation_path` (e.g. `FDA > 21 CFR Part 11 > §11.10 > (e)`) is stored verbatim on the chunk |
| **Regulatory Intelligence** | No way to ask "show me every Data Integrity requirement across FDA + EMA" | `gxp_area`, `compliance_domain`, `topic`, `chunk_type` support cross-document, cross-authority filtering via ChromaDB `where` clauses |
| **Retrieval Accuracy** | Token-bounded chunks can split a single requirement mid-sentence, or bury it inside adjacent unrelated text | Requirement-level chunks keep retrieval focused: a query about "audit trails" returns 11.10(e) specifically, not a paragraph mixing training, validation, and audit trail requirements |
| **Impact Analysis** | No structured way to answer "which SOPs reference 21 CFR 211.100(a)?" | `document_id`/`section`/`paragraph` fields make it possible to trace a specific citation across every ingested document (regulations today; SOPs/CAPAs/deviations in later phases via `chunk_type`) |

---

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI + Uvicorn |
| PDF parsing | pypdf |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`, runs locally) |
| Vector DB | ChromaDB (persisted to `./chroma_db/`) |
| Frontend | React (JSX) |

---

## Backend Setup

```bash
# Install dependencies
python -m venv .venv
# Windows: .venv\Scripts\activate | macOS/Linux: source .venv/bin/activate
.venv\Scripts\activate

pip install -r requirements.txt

# Run the FastAPI server
uvicorn main:app --reload --port 8000
```

The first startup downloads the embedding model (~80 MB). Subsequent starts are instant.

API docs available at http://localhost:8000/docs

---

## Frontend setup

Scaffold a Vite React project (skip if you already have one):

```bash
npm create vite@latest frontend -- --template react
cd frontend
npm install
```

Copy `src/App.jsx` into the project, replacing the default one, then:

```bash
npm run dev   # starts on http://localhost:3000
```

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/upload` | Upload a PDF (multipart/form-data: `file`, `doc_type`, plus optional `authority`, `regulation`, `regulation_family`, `title`, `effective_date`, `version`, `status`, `source_url`) |
| `GET` | `/documents` | List all indexed documents |
| `GET` | `/documents/{doc_id}/markdown` | Converted Markdown, for spot-checking Docling's conversion |
| `GET` | `/documents/{doc_id}/pdf` | Original PDF — the audit system of record |
| `DELETE` | `/documents/{doc_id}` | Remove a document and all its chunks |
| `POST` | `/query` | Semantic search `{ query, top_k, filters }` — `filters` is an optional ChromaDB `where` map, e.g. `{"authority": "FDA"}` or `{"authority": "FDA", "chunk_type": "regulatory_requirement"}` |
| `POST` | `/ask` | Retrieval-augmented answer via local Ollama, grounded in cited chunks |
| `GET` | `/doc-types` | Allowed `doc_type` values (drives the upload form's dropdown) |
| `GET` | `/health` | Health check + total chunk count |

`authority`/`country` are auto-detected from the document text when not
supplied explicitly (see `AUTHORITY_PATTERNS` in `config.py`); every other
compliance field defaults to `"unknown"` rather than being omitted.

---

## Configuration

Edit the constants in `config.py`:

```python
CHROMA_PATH        = "./chroma_db"        # where ChromaDB persists data
EMBED_MODEL        = "all-MiniLM-L6-v2"   # sentence-transformers model, runs locally
MAX_CHUNK_TOKENS   = 256                  # embedding model's max sequence length
MAX_PARAGRAPH_CHARS = 1000                # oversized-obligation split threshold
DOC_TYPE_METADATA   = {...}               # doc_type -> (document_type, chunk_type)
AUTHORITY_PATTERNS  = [...]               # regex -> (authority, country) auto-detection
TOPIC_KEYWORDS / GXP_AREA_KEYWORDS / COMPLIANCE_DOMAIN_KEYWORDS = {...}  # metadata enrichment
```

---

## Running tests

```bash
pytest test_regulatory_parser.py -v
```

The parser tests run against synthetic Markdown directly — no PDF, Docling,
or embedding model required, so they're fast and fully offline.

---

## Notes

- Scanned / image-only PDFs will fail (no extractable text layer). Use an OCR pre-processor like `pytesseract` or `ocrmypdf` first.
- ChromaDB uses cosine similarity. Scores in the UI are `1 − distance` (1 = identical).
- **On-premises is a hard requirement, not a default.** Documents are
  regulated content (FDA/EMA/ICH/Swissmedic filings, and in later phases
  SOPs, CAPAs, deviations) that must never leave local infrastructure. The
  embedding model (`sentence-transformers`) and the answer-generation model
  (local Ollama, see `ollama_client.py`) both run fully on-device — do not
  swap either for a cloud API (OpenAI, Cohere, Azure AI Foundry, Anthropic,
  or any hosted "OpenAI-compatible" endpoint), including for "production."
  If a Microsoft-branded runtime is ever wanted, use on-device Foundry
  Local, never the Azure AI Foundry cloud service.
