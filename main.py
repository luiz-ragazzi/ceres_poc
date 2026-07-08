"""
Compliance Document RAG POC - FastAPI Backend
Uploads PDFs, converts them to Markdown via Docling for heading-aware
chunking, embeds chunks with sentence-transformers, and stores them in a
local ChromaDB vector database. Original PDFs and converted Markdown are
kept on disk as the audit-trail system of record, independent of Chroma.
"""

import os
import uuid
from datetime import datetime
from typing import List

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse

import registry
from config import CORS_ORIGINS, DOCUMENTS_PATH, DOC_TYPES
from embedder import get_embedder
from database import get_database
from ollama_client import generate_answer, OllamaUnavailableError
from pdf_processor import process_pdf, sha256_of
from models import AskResponse, QueryRequest, QueryResult, DocumentInfo

# ─── App Setup ───────────────────────────────────────────────────────────────

app = FastAPI(title="Compliance Document RAG POC", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(DOCUMENTS_PATH, exist_ok=True)

# Initialize singletons at startup
db = get_database()
embedder = get_embedder()


@app.get("/")
def root():
    return {"status": "ok", "message": "Compliance Document RAG POC backend running"}


@app.get("/health")
def health():
    total = db.count()
    return {"status": "ok", "total_chunks": total}


@app.get("/doc-types")
def doc_types():
    """Allowed doc_type values, so the UI's dropdown stays in sync with the backend."""
    return DOC_TYPES


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...), doc_type: str = Form("Other")):
    """
    Upload a PDF -> save original -> convert to Markdown via Docling ->
    heading-aware chunk -> embed -> store in ChromaDB.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    if doc_type not in DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"doc_type must be one of {DOC_TYPES}")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    doc_id = str(uuid.uuid4())
    uploaded_at = datetime.utcnow().isoformat()

    try:
        markdown_text, chunks, embeddings, pdf_path, md_path, page_count = process_pdf(
            doc_id, contents
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not process PDF: {e}")

    if not markdown_text.strip():
        raise HTTPException(
            status_code=422,
            detail="No extractable content found in PDF (scanned/image-only?).",
        )

    if not chunks:
        raise HTTPException(status_code=422, detail="Chunking produced no results.")

    ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "doc_id": doc_id,
            "filename": file.filename,
            "doc_type": doc_type,
            "chunk_index": i,
            "section_path": c["section_path"],
            "pages": ",".join(str(p) for p in c["pages"]),
            "uploaded_at": uploaded_at,
        }
        for i, c in enumerate(chunks)
    ]

    db.add_documents(
        ids=ids,
        embeddings=embeddings,
        documents=[c["text"] for c in chunks],
        metadatas=metadatas,
    )

    registry.add_document(
        doc_id=doc_id,
        filename=file.filename,
        doc_type=doc_type,
        original_path=pdf_path,
        markdown_path=md_path,
        sha256=sha256_of(contents),
        page_count=page_count,
        chunk_count=len(chunks),
        uploaded_at=uploaded_at,
    )

    return {
        "doc_id": doc_id,
        "filename": file.filename,
        "doc_type": doc_type,
        "chunk_count": len(chunks),
        "page_count": page_count,
        "uploaded_at": uploaded_at,
    }


def _retrieve(query_text: str, top_k: int) -> List[QueryResult]:
    """Embed the query and return top-k similar chunks with citation metadata."""
    if not query_text.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    if db.count() == 0:
        raise HTTPException(status_code=404, detail="No documents indexed yet. Upload a PDF first.")

    query_embedding = embedder.encode([query_text])

    results = db.query(
        query_embeddings=query_embedding,
        n_results=min(top_k, db.count()),
    )

    output = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        output.append(
            QueryResult(
                chunk=doc,
                source=meta.get("filename", "unknown"),
                score=round(1 - dist, 4),   # cosine similarity (1 = identical)
                chunk_index=meta.get("chunk_index", -1),
                section_path=meta.get("section_path", ""),
                pages=meta.get("pages", ""),
                doc_type=meta.get("doc_type", ""),
            )
        )

    return output


@app.post("/query", response_model=List[QueryResult])
def query(req: QueryRequest):
    """
    Semantic search: embed the query and return top-k similar chunks.
    """
    return _retrieve(req.query, req.top_k)


@app.post("/ask", response_model=AskResponse)
def ask(req: QueryRequest):
    """
    Retrieval-augmented answer: retrieve top-k chunks, then have a local
    Ollama model synthesize a grounded answer, citing chunk sources.
    """
    chunks = _retrieve(req.query, req.top_k)

    try:
        answer = generate_answer(req.query, chunks)
    except OllamaUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return AskResponse(answer=answer, sources=chunks)


@app.get("/documents", response_model=List[DocumentInfo])
def list_documents():
    """
    Return all actively indexed documents from the registry (independent of
    Chroma, so this stays accurate even across a vector index rebuild).
    """
    return [
        DocumentInfo(
            doc_id=d["doc_id"],
            filename=d["filename"],
            doc_type=d["doc_type"],
            page_count=d["page_count"],
            chunk_count=d["chunk_count"],
            uploaded_at=d["uploaded_at"],
        )
        for d in registry.list_active_documents()
    ]


@app.get("/documents/{doc_id}/markdown", response_class=PlainTextResponse)
def get_document_markdown(doc_id: str):
    """Return the converted Markdown, for spot-checking conversion quality."""
    doc = registry.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"No document found with id '{doc_id}'.")
    with open(doc["markdown_path"], "r", encoding="utf-8") as f:
        return f.read()


@app.get("/documents/{doc_id}/pdf")
def get_document_pdf(doc_id: str):
    """Return the original PDF — the audit system of record."""
    doc = registry.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"No document found with id '{doc_id}'.")
    return FileResponse(doc["original_path"], media_type="application/pdf", filename=doc["filename"])


@app.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    """
    Remove a document from the searchable index. The original PDF and
    converted Markdown are kept on disk for audit purposes.
    """
    doc = registry.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"No document found with id '{doc_id}'.")

    deleted_count = db.delete_by_doc_id(doc_id)
    registry.soft_delete(doc_id, datetime.utcnow().isoformat())

    return {"deleted_chunks": deleted_count, "doc_id": doc_id, "files_retained": True}
