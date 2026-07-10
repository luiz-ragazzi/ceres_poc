# PDF RAG POC

A minimal full-stack app to upload PDFs, store their embeddings locally, and run semantic search.

## Project Structure

```
compliance-assistant-poc/
├── Backend (Python modules with separation of concerns)
│   ├── main.py              ← FastAPI application entry point
│   ├── config.py            ← Configuration management
│   ├── database.py          ← Database operations
│   ├── embedder.py          ← Embedding model handling
│   ├── models.py            ← Data models
│   ├── pdf_processor.py     ← PDF processing logic
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
└── chroma_db/               ← Vector database storage (persisted locally)
```

---

## Backend Module Architecture

The backend follows a **separation of concerns** pattern with each module handling a specific responsibility:

| Module | Responsibility |
|---|---|
| `main.py` | FastAPI application, route definitions, request/response handling |
| `config.py` | Configuration constants and settings management |
| `database.py` | ChromaDB operations and document management |
| `embedder.py` | Embedding model initialization and inference |
| `models.py` | Data models and schemas (Pydantic models, type definitions) |
| `pdf_processor.py` | PDF parsing, text extraction, and chunking logic |

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
| `POST` | `/upload` | Upload a PDF (multipart/form-data, field `file`) |
| `GET` | `/documents` | List all indexed documents |
| `DELETE` | `/documents/{doc_id}` | Remove a document and all its chunks |
| `POST` | `/query` | Semantic search `{ query, top_k }` |
| `GET` | `/health` | Health check + total chunk count |

---

## Configuration

Edit the constants in `config.py`:

```python
CHROMA_PATH   = "./chroma_db"   # where ChromaDB persists data
CHUNK_SIZE    = 500             # characters per chunk
CHUNK_OVERLAP = 50              # overlap between consecutive chunks
EMBED_MODEL   = "all-MiniLM-L6-v2"
```

---

## Notes

- Scanned / image-only PDFs will fail (no extractable text layer). Use an OCR pre-processor like `pytesseract` or `ocrmypdf` first.
- The embedding model runs fully locally — no API key required.
- ChromaDB uses cosine similarity. Scores in the UI are `1 − distance` (1 = identical).
- For production use, swap ChromaDB for Qdrant/Weaviate/pgvector and `sentence-transformers` for an OpenAI/Cohere embedding API.
