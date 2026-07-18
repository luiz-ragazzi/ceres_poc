"""
Compliance Document RAG POC - FastAPI Backend
Uploads PDFs, converts them to Markdown via Docling, chunks them by
regulatory structure (Part/Subpart/Section/Paragraph — see
regulatory_parser.py), embeds chunks with sentence-transformers, and
stores them with full compliance metadata (regulatory_metadata.py) in a
local ChromaDB vector database. Original PDFs and converted Markdown are
kept on disk as the audit-trail system of record, independent of Chroma.
"""

import os
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse

import registry
from config import CORS_ORIGINS, DOCUMENTS_PATH, DOC_TYPES, DOC_TYPE_METADATA
from embedder import get_embedder
from database import get_database
from ollama_client import generate_answer, OllamaUnavailableError
from pdf_processor import (
    chunk_and_embed,
    convert_to_markdown,
    detect_document_authority,
    pages_for_chunk,
    save_original_pdf,
    sha256_of,
)
from regulatory_metadata import UNKNOWN
from regulatory_parser import DocumentContext, regulation_slug
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
async def upload_pdf(
    file: UploadFile = File(...),
    doc_type: str = Form("Other"),
    authority: Optional[str] = Form(None),
    regulation: Optional[str] = Form(None),
    regulation_family: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    effective_date: Optional[str] = Form(None),
    version: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    source_url: Optional[str] = Form(None),
):
    """
    Upload a PDF -> save original -> convert to Markdown via Docling ->
    regulatory structure chunk (Part/Subpart/Section/Paragraph) -> embed ->
    store in ChromaDB with full compliance metadata.

    authority/regulation/etc. are optional: authority and its country are
    auto-detected from the document text when not supplied explicitly.
    Every other unresolved field is stored as "unknown" rather than
    omitted, per the mandatory metadata schema (regulatory_metadata.py).
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

    document_type, chunk_type = DOC_TYPE_METADATA[doc_type]

    try:
        # Authority auto-detection needs the converted Markdown, so convert
        # first and build the DocumentContext once we know it, rather than
        # guessing up front.
        pdf_path = save_original_pdf(doc_id, contents)
        document, markdown_text, md_path = convert_to_markdown(doc_id, pdf_path)

        detected_authority, detected_country = detect_document_authority(markdown_text, file.filename)
        resolved_authority = authority or detected_authority
        resolved_regulation = regulation or UNKNOWN
        reg_slug = regulation_slug(resolved_regulation)
        document_id = (
            f"{resolved_authority}_{reg_slug}"
            if resolved_authority != UNKNOWN and reg_slug != UNKNOWN
            else doc_id
        )

        context = DocumentContext(
            document_id=document_id,
            authority=resolved_authority,
            country=detected_country if not authority else UNKNOWN,
            document_type=document_type,
            regulation_family=regulation_family or UNKNOWN,
            regulation=resolved_regulation,
            title=title or UNKNOWN,
            chunk_type=chunk_type,
            effective_date=effective_date or UNKNOWN,
            version=version or UNKNOWN,
            status=status or UNKNOWN,
            source_url=source_url or UNKNOWN,
        )

        chunks, embeddings, page_map = chunk_and_embed(document, markdown_text, context)
        page_count = document.num_pages()
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not process PDF: {e}")

    if not markdown_text.strip():
        raise HTTPException(
            status_code=422,
            detail="No extractable content found in PDF (scanned/image-only?).",
        )

    if not chunks:
        raise HTTPException(status_code=422, detail="Chunking produced no results.")

    ids = [f"{doc_id}_{i}_{c.metadata.chunk_id}" for i, c in enumerate(chunks)]
    metadatas = []
    for i, c in enumerate(chunks):
        meta = c.metadata.to_chroma_metadata()
        pages = pages_for_chunk(c, page_map)
        meta.update(
            {
                "doc_id": doc_id,
                "filename": file.filename,
                "doc_type": doc_type,
                "chunk_index": i,
                "section_path": meta["citation_path"] if meta["citation_path"] != UNKNOWN else (c.heading_title or UNKNOWN),
                "pages": ",".join(str(p) for p in pages),
                "uploaded_at": uploaded_at,
            }
        )
        metadatas.append(meta)

    db.add_documents(
        ids=ids,
        embeddings=embeddings,
        documents=[c.text for c in chunks],
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
        "document_id": document_id,
        "filename": file.filename,
        "doc_type": doc_type,
        "authority": resolved_authority,
        "chunk_count": len(chunks),
        "page_count": page_count,
        "uploaded_at": uploaded_at,
    }


def _retrieve(query_text: str, top_k: int, filters: Optional[dict] = None) -> List[QueryResult]:
    """
    Embed the query and return top-k similar chunks with full citation
    metadata, optionally narrowed by a compliance filter (e.g.
    {"authority": "FDA"} or {"authority": "FDA", "chunk_type":
    "regulatory_requirement"}), enabling compliance-scoped retrieval.
    """
    if not query_text.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    if db.count() == 0:
        raise HTTPException(status_code=404, detail="No documents indexed yet. Upload a PDF first.")

    query_embedding = embedder.encode([query_text])

    results = db.query(
        query_embeddings=query_embedding,
        n_results=min(top_k, db.count()),
        where=filters,
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
                chunk_id=meta.get("chunk_id", "unknown"),
                authority=meta.get("authority", "unknown"),
                regulation=meta.get("regulation", "unknown"),
                part=meta.get("part", "unknown"),
                subpart=meta.get("subpart", "unknown"),
                section=meta.get("section", "unknown"),
                paragraph=meta.get("paragraph", "unknown"),
                topic=meta.get("topic", "unknown"),
                gxp_area=meta.get("gxp_area", "unknown"),
                compliance_domain=meta.get("compliance_domain", "unknown"),
                chunk_type=meta.get("chunk_type", "unknown"),
                citation_path=meta.get("citation_path", "unknown"),
            )
        )

    return output


@app.post("/query", response_model=List[QueryResult])
def query(req: QueryRequest):
    """
    Semantic search: embed the query and return top-k similar chunks,
    optionally scoped by compliance metadata filters (req.filters).
    """
    return _retrieve(req.query, req.top_k, req.filters)


@app.post("/ask", response_model=AskResponse)
def ask(req: QueryRequest):
    """
    Retrieval-augmented answer: retrieve top-k chunks, then have a local
    Ollama model synthesize a grounded answer, citing chunk sources.
    """
    chunks = _retrieve(req.query, req.top_k, req.filters)

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
