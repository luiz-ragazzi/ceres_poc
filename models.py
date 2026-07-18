"""
Pydantic models for request/response validation.
"""

from pydantic import BaseModel
from typing import Dict, List, Optional


class QueryRequest(BaseModel):
    """Request model for semantic search."""
    query: str
    top_k: int = 5
    # Compliance retrieval filters, e.g. {"authority": "FDA"} or
    # {"authority": "FDA", "chunk_type": "regulatory_requirement"}.
    # Passed straight through to ChromaDB's `where` clause.
    filters: Optional[Dict[str, str]] = None


class QueryResult(BaseModel):
    """Individual query result, with full regulatory citation metadata."""
    chunk: str
    source: str
    score: float
    chunk_index: int
    section_path: str = ""
    pages: str = ""
    doc_type: str = ""
    # Regulatory traceability (requirement_metadata.ChunkMetadata subset)
    chunk_id: str = "unknown"
    authority: str = "unknown"
    regulation: str = "unknown"
    part: str = "unknown"
    subpart: str = "unknown"
    section: str = "unknown"
    paragraph: str = "unknown"
    topic: str = "unknown"
    gxp_area: str = "unknown"
    compliance_domain: str = "unknown"
    chunk_type: str = "unknown"
    citation_path: str = "unknown"


class AskResponse(BaseModel):
    """Grounded, LLM-synthesized answer plus the chunks it was built from."""
    answer: str
    sources: List[QueryResult]


class DocumentInfo(BaseModel):
    """Document information in the collection."""
    doc_id: str
    filename: str
    doc_type: str
    page_count: int | None = None
    chunk_count: int
    uploaded_at: str
