"""
Document processing pipeline: save original PDF, convert to Markdown via
Docling, chunk along the heading tree, and embed the chunks.

PDFs are kept on disk as the system of record (exact pagination/formatting
for audit purposes). Markdown is a derived, human-inspectable intermediate
that gives the chunker a real heading hierarchy instead of guessing
structure from font size in raw PDF text.
"""

import hashlib
import os
from typing import Any, Dict, List, Tuple

from docling.chunking import HybridChunker
from docling.document_converter import DocumentConverter
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from transformers import AutoTokenizer

from config import DOCUMENTS_PATH, EMBED_MODEL, MAX_CHUNK_TOKENS
from embedder import get_embedder

_converter = DocumentConverter()

_tokenizer = HuggingFaceTokenizer(
    tokenizer=AutoTokenizer.from_pretrained(f"sentence-transformers/{EMBED_MODEL}"),
    max_tokens=MAX_CHUNK_TOKENS,
)
_chunker = HybridChunker(
    tokenizer=_tokenizer,
    # Keep chunks aligned 1:1 with a single heading section — for audit
    # citations, precise section attribution matters more than avoiding a
    # few small chunks.
    merge_peers=False,
)


def sha256_of(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def save_original_pdf(doc_id: str, file_bytes: bytes) -> str:
    """Persist the original PDF bytes untouched — the audit system of record."""
    doc_dir = os.path.join(DOCUMENTS_PATH, doc_id)
    os.makedirs(doc_dir, exist_ok=True)
    pdf_path = os.path.join(doc_dir, "original.pdf")
    with open(pdf_path, "wb") as f:
        f.write(file_bytes)
    return pdf_path


def convert_to_markdown(doc_id: str, pdf_path: str) -> Tuple[Any, str, str]:
    """Run Docling's layout-aware PDF parser and export the result as Markdown."""
    result = _converter.convert(pdf_path)
    document = result.document
    markdown_text = document.export_to_markdown()

    md_path = os.path.join(DOCUMENTS_PATH, doc_id, "converted.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown_text)

    return document, markdown_text, md_path


def chunk_document(document: Any) -> List[Dict[str, Any]]:
    """
    Heading-aware chunking via Docling's HybridChunker: it walks the parsed
    document tree, groups content under its heading hierarchy, keeps tables
    intact, and token-bounds each chunk to the embedding model's context
    window (merging small sibling sections, splitting oversized ones).
    """
    chunks = []
    for raw_chunk in _chunker.chunk(dl_doc=document):
        pages = sorted({
            prov.page_no
            for item in raw_chunk.meta.doc_items
            for prov in item.prov
        })
        chunks.append({
            "text": raw_chunk.text,
            # heading path prefixed in — improves retrieval relevance
            "embed_text": _chunker.contextualize(chunk=raw_chunk),
            "section_path": " > ".join(raw_chunk.meta.headings or []),
            "pages": pages,
        })
    return chunks


def embed_chunks(chunks: List[Dict[str, Any]]) -> List[List[float]]:
    embedder = get_embedder()
    return embedder.encode([c["embed_text"] for c in chunks])


def process_pdf(doc_id: str, file_bytes: bytes) -> Tuple[str, List[Dict[str, Any]], List[List[float]], str, str, int]:
    """
    Full pipeline: save original -> Docling convert to Markdown ->
    heading-aware chunk -> embed.

    Returns (markdown_text, chunks, embeddings, pdf_path, md_path, page_count).
    """
    pdf_path = save_original_pdf(doc_id, file_bytes)
    document, markdown_text, md_path = convert_to_markdown(doc_id, pdf_path)
    chunks = chunk_document(document)
    embeddings = embed_chunks(chunks)
    return markdown_text, chunks, embeddings, pdf_path, md_path, document.num_pages()
