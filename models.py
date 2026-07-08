"""
Pydantic models for request/response validation.
"""

from pydantic import BaseModel
from typing import List


class QueryRequest(BaseModel):
    """Request model for semantic search."""
    query: str
    top_k: int = 5


class QueryResult(BaseModel):
    """Individual query result."""
    chunk: str
    source: str
    score: float
    chunk_index: int
    section_path: str = ""
    pages: str = ""
    doc_type: str = ""


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
