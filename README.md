# Compliance Document RAG POC

A full-stack app to upload regulatory PDFs (SOPs, CTDs, CAPA records, audit reports), convert them to
heading-structured Markdown via Docling, store their embeddings locally, and run semantic search.

> **Hard requirement: on-premises only.** Documents are regulated content that must never leave local
> infrastructure. Embeddings (`sentence-transformers`) and answer generation (Ollama) both run locally.
> Do not swap `OLLAMA_HOST` for a cloud API (Azure AI Foundry, OpenAI, Anthropic, etc.) — see the
> warning comment in `config.py`.

## Project Structure

```
compliance-assistant-poc/
├── Backend (Python modules with separation of concerns)
│   ├── main.py              ← FastAPI application entry point
│   ├── config.py            ← Configuration management
│   ├── database.py          ← ChromaDB (vector search) operations
│   ├── registry.py          ← SQLite doc registry (file paths, audit metadata)
│   ├── embedder.py          ← Embedding model handling
│   ├── models.py            ← Data models
│   ├── pdf_processor.py     ← Docling conversion + heading-aware chunking
│   ├── ollama_client.py     ← Grounded answer synthesis via local Ollama
│   └── requirements.txt     ← Python dependencies
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
├── documents/                ← Per-doc_id original.pdf + converted.md + registry.db (system of record)
└── chroma_db/                ← Vector database storage (persisted locally, safe to rebuild)
```

---

## Document Pipeline

```
PDF upload
  │
  ├─► saved untouched to documents/<doc_id>/original.pdf   (audit system of record —
  │                                                          exact pagination/formatting)
  │
  ├─► Docling DocumentConverter → DoclingDocument
  │     └─► export_to_markdown() → documents/<doc_id>/converted.md
  │                                 (human-readable, spot-checkable conversion)
  │
  ├─► Docling HybridChunker walks the document's heading tree:
  │     • groups content under its section heading path (e.g. "5. Stage 2 > 5.2 PPQ > 5.2.1 Media Fill")
  │     • keeps tables intact
  │     • token-bounds each chunk to the embedding model's context window
  │     • merges undersized sibling sections, splits oversized ones
  │
  ├─► sentence-transformers embeds each chunk (heading path included as context)
  │
  ├─► chunks + embeddings + metadata (doc_id, section_path, pages, doc_type) → ChromaDB
  │
  └─► doc_id → file paths / hash / page count → registry.py (SQLite, independent of Chroma)
```

Deleting a document removes it from the searchable Chroma index but **keeps** `original.pdf` and
`converted.md` on disk — the registry row is soft-deleted (`deleted_at` set), not dropped.

`POST /ask` runs the same retrieval as `/query`, then sends the top-k chunks — each labeled with its
`section_path` and `pages` — to a local Ollama model, which is instructed to answer only from those
excerpts and cite them (e.g. `[1]`). The API response includes both the synthesized `answer` and the
`sources` list so you can verify every citation against the actual retrieved text.

---

## Backend Module Architecture

| Module | Responsibility |
|---|---|
| `main.py` | FastAPI application, route definitions, request/response handling |
| `config.py` | Configuration constants and settings management |
| `database.py` | ChromaDB vector operations |
| `registry.py` | SQLite sidecar mapping doc_id → original/markdown paths, doc_type, hash, page/chunk counts |
| `embedder.py` | Embedding model initialization and inference |
| `models.py` | Data models and schemas (Pydantic models, type definitions) |
| `pdf_processor.py` | PDF persistence, Docling conversion, heading-aware chunking |
| `ollama_client.py` | Builds the grounded prompt and calls the local Ollama chat API |

---

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI + Uvicorn |
| PDF → Markdown | Docling (IBM) — layout-aware, heading + table structure preserved |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`, runs locally) |
| Vector DB | ChromaDB (persisted to `./chroma_db/`) |
| Document registry | SQLite (`./documents/registry.db`) |
| Answer generation | Ollama (`llama3.2:latest`, runs locally) |
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

```bash
cd frontend
npm install
npm run dev   # starts on http://localhost:5173
```

`App.jsx` (both here and mirrored at the repo root) implements two views, styled after the
"Methodos" design system:

- **Query console** (default view) — chat-style interface. Suggestion prompts, a composer, and
  answers rendered with citation chips (`source · section_path · p.pages · doc_type`). Calls `POST /ask`.
- **Configuration** — document-type selector (populated from `GET /doc-types`), a drag-and-drop
  upload panel with real upload progress, and a table of indexed documents with delete.

The doc-strip under the header shows a live `DOCS INDEXED` count fetched on load, independent of
which view is active.

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/upload` | Upload a PDF (multipart/form-data, fields `file`, `doc_type`) |
| `GET` | `/documents` | List all actively indexed documents (includes `page_count`) |
| `GET` | `/documents/{doc_id}/markdown` | Fetch the converted Markdown (spot-check conversion quality) |
| `GET` | `/documents/{doc_id}/pdf` | Download the original PDF (audit system of record) |
| `DELETE` | `/documents/{doc_id}` | Remove a document from the search index (files retained on disk) |
| `POST` | `/query` | Semantic search `{ query, top_k }` → ranked chunks |
| `POST` | `/ask` | Retrieval + Ollama-synthesized answer `{ query, top_k }` → `{ answer, sources }` |
| `GET` | `/doc-types` | Allowed `doc_type` values — the frontend's dropdown reads this instead of hardcoding a copy |
| `GET` | `/health` | Health check + total chunk count |

`doc_type` must be one of `config.DOC_TYPES`: `SOP`, `CTD`, `CAPA`, `Audit Report`, `Guidance Document`, `Other`.

---

## Configuration

Edit the constants in `config.py`:

```python
CHROMA_PATH      = "./chroma_db"        # where ChromaDB persists vectors
DOCUMENTS_PATH   = "./documents"        # original PDFs + converted Markdown (system of record)
REGISTRY_DB_PATH = "./documents/registry.db"
EMBED_MODEL      = "all-MiniLM-L6-v2"
MAX_CHUNK_TOKENS = 256                  # chunk size cap, matches EMBED_MODEL's context window
DOC_TYPES        = ["SOP", "CTD", "CAPA", "Audit Report", "Guidance Document", "Other"]
OLLAMA_HOST      = "http://127.0.0.1:11434"
OLLAMA_MODEL     = "llama3.2:latest"    # swap for a larger local model if you need stronger reasoning
OLLAMA_TIMEOUT   = 120                  # seconds
```

Requires the Ollama app/server running locally with `OLLAMA_MODEL` pulled (`ollama pull llama3.2`).

---

## Notes

- Scanned / image-only PDFs: Docling includes built-in OCR (via `rapidocr`) and will attempt it
  automatically when no text layer is found; quality varies, so spot-check the resulting `converted.md`.
- The embedding model runs fully locally — no API key required.
- ChromaDB uses cosine similarity. Scores in the UI are `1 − distance` (1 = identical).
- `/ask` is grounded but not guaranteed hallucination-free — the system prompt instructs the model to
  cite excerpts and say "not found" when the context is insufficient, but always verify against `sources`
  before relying on an answer for a compliance decision.
- For production use, swap ChromaDB for Qdrant/Weaviate/pgvector and consider a hosted embedding API.
