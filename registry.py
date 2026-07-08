"""
Independent document registry.

Tracks doc_id -> original PDF / converted Markdown on disk, decoupled from
Chroma's lifecycle so the audit trail (which file was filed, when, as what
type) survives even if the vector index is rebuilt or wiped.
"""

import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from config import DOCUMENTS_PATH, REGISTRY_DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    original_path TEXT NOT NULL,
    markdown_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    page_count INTEGER,
    chunk_count INTEGER,
    uploaded_at TEXT NOT NULL,
    deleted_at TEXT
);
"""


@contextmanager
def _connect():
    os.makedirs(DOCUMENTS_PATH, exist_ok=True)
    conn = sqlite3.connect(REGISTRY_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def add_document(
    doc_id: str,
    filename: str,
    doc_type: str,
    original_path: str,
    markdown_path: str,
    sha256: str,
    page_count: int,
    chunk_count: int,
    uploaded_at: str,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO documents
                (doc_id, filename, doc_type, original_path, markdown_path,
                 sha256, page_count, chunk_count, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (doc_id, filename, doc_type, original_path, markdown_path,
             sha256, page_count, chunk_count, uploaded_at),
        )


def soft_delete(doc_id: str, deleted_at: str) -> None:
    """Remove a document from the active index while keeping its files on disk."""
    with _connect() as conn:
        conn.execute(
            "UPDATE documents SET deleted_at = ? WHERE doc_id = ?",
            (deleted_at, doc_id),
        )


def get_document(doc_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        return dict(row) if row else None


def list_active_documents() -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM documents WHERE deleted_at IS NULL ORDER BY uploaded_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
