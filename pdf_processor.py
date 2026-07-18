"""
Document processing pipeline: save original PDF, convert to Markdown via
Docling, chunk by regulatory structure (Part/Subpart/Section/Paragraph),
and embed the chunks.

PDFs are kept on disk as the system of record (exact pagination/formatting
for audit purposes). Markdown is a derived, human-inspectable intermediate
that gives the regulatory parser a real heading hierarchy instead of
guessing structure from font size in raw PDF text.

Docling's HybridChunker is still used, but only as a page-number locator:
it walks the parsed document tree with page provenance attached, which we
use to look up which PDF page(s) a given heading's content came from. The
actual chunk boundaries — one chunk per regulatory obligation — come from
regulatory_parser.create_regulatory_chunks(), not from HybridChunker.
"""

import hashlib
import os
from typing import Any, Dict, List, Tuple

from docling.chunking import HybridChunker
from docling.document_converter import DocumentConverter
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from transformers import AutoTokenizer

from config import AUTHORITY_PATTERNS, DOCUMENTS_PATH, EMBED_MODEL, MAX_CHUNK_TOKENS
from embedder import get_embedder
from regulatory_metadata import UNKNOWN
from regulatory_parser import DocumentContext, RegulatoryChunk, create_regulatory_chunks, detect_authority

_converter = DocumentConverter()

_tokenizer = HuggingFaceTokenizer(
    tokenizer=AutoTokenizer.from_pretrained(f"sentence-transformers/{EMBED_MODEL}"),
    max_tokens=MAX_CHUNK_TOKENS,
)
_chunker = HybridChunker(
    tokenizer=_tokenizer,
    # Keep chunks aligned 1:1 with a single heading section — needed for
    # the page-number lookup in _build_heading_page_map to stay precise.
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


def _build_heading_page_map(document: Any) -> Dict[str, List[int]]:
    """
    Best-effort page lookup per heading: run Docling's HybridChunker once
    purely to get page provenance, then key it by the heading text itself
    so regulatory_parser's section titles (parsed independently from the
    same markdown) can look up which PDF page(s) they came from.
    """
    page_map: Dict[str, List[int]] = {}
    for raw_chunk in _chunker.chunk(dl_doc=document):
        headings = raw_chunk.meta.headings or []
        if not headings:
            continue
        pages = {prov.page_no for item in raw_chunk.meta.doc_items for prov in item.prov}
        key = headings[-1].strip().lower()
        existing = page_map.setdefault(key, set())
        existing.update(pages)
    return {k: sorted(v) for k, v in page_map.items()}


def detect_document_authority(markdown_text: str, filename: str) -> Tuple[str, str]:
    """Auto-detect (authority, country) from document title/text/filename."""
    authority, country = detect_authority(markdown_text[:2000], AUTHORITY_PATTERNS)
    if authority == UNKNOWN:
        authority, country = detect_authority(filename, AUTHORITY_PATTERNS)
    return authority, country


def pages_for_chunk(chunk: RegulatoryChunk, page_map: Dict[str, List[int]]) -> List[int]:
    """Best-effort PDF page(s) for a chunk, via its section heading title."""
    return page_map.get(chunk.heading_title.strip().lower(), [])


def embed_chunks(chunks: List[RegulatoryChunk]) -> List[List[float]]:
    embedder = get_embedder()
    return embedder.encode([c.embed_text for c in chunks])


def chunk_and_embed(
    document: Any,
    markdown_text: str,
    context: DocumentContext,
) -> Tuple[List[RegulatoryChunk], List[List[float]], Dict[str, List[int]]]:
    """
    Regulatory-structure chunk an already-converted document and embed the
    result. Split out from process_pdf() so callers that need to inspect
    the Markdown (e.g. to auto-detect `authority` before finalizing the
    DocumentContext) can convert once and chunk afterward instead of
    converting the PDF twice.
    """
    page_map = _build_heading_page_map(document)
    chunks = create_regulatory_chunks(markdown_text, context)
    embeddings = embed_chunks(chunks)
    return chunks, embeddings, page_map


def process_pdf(
    doc_id: str,
    file_bytes: bytes,
    context: DocumentContext,
) -> Tuple[str, List[RegulatoryChunk], List[List[float]], str, str, int, Dict[str, List[int]]]:
    """
    Full pipeline: save original -> Docling convert to Markdown ->
    regulatory structure chunk -> embed. Use this when the DocumentContext
    (authority, regulation, ...) is already fully known; otherwise convert
    first and call chunk_and_embed() once authority has been auto-detected.

    Returns (markdown_text, chunks, embeddings, pdf_path, md_path,
    page_count, heading_page_map). heading_page_map lets the caller look up
    approximate PDF page(s) per chunk via its section heading title.
    """
    pdf_path = save_original_pdf(doc_id, file_bytes)
    document, markdown_text, md_path = convert_to_markdown(doc_id, pdf_path)
    chunks, embeddings, page_map = chunk_and_embed(document, markdown_text, context)
    return markdown_text, chunks, embeddings, pdf_path, md_path, document.num_pages(), page_map
