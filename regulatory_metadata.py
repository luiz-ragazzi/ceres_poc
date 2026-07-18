"""
Mandatory metadata schema for regulatory chunks.

Every chunk stored in the platform — regardless of authority or document
type — carries the same fields. A field that cannot be determined is set to
UNKNOWN rather than omitted, so downstream ChromaDB `where` filters and
audit exports never have to special-case a missing key.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict

from config import CHUNK_TYPES

UNKNOWN = "unknown"


@dataclass(frozen=True)
class Citation:
    """Human- and machine-readable pointer back to the exact regulatory source."""

    authority: str = UNKNOWN
    regulation: str = UNKNOWN
    section: str = UNKNOWN
    paragraph: str = UNKNOWN

    def as_dict(self) -> Dict[str, str]:
        return asdict(self)

    def path(self) -> str:
        """e.g. 'FDA > 21 CFR Part 11 > §11.10 > (e)'"""
        parts = []
        if self.authority != UNKNOWN:
            parts.append(self.authority)
        if self.regulation != UNKNOWN:
            parts.append(self.regulation)
        if self.section != UNKNOWN:
            parts.append(f"§{self.section}")
        if self.paragraph != UNKNOWN:
            parts.append(f"({self.paragraph})")
        return " > ".join(parts) if parts else UNKNOWN


@dataclass
class ChunkMetadata:
    """Mandatory metadata attached to every regulatory chunk."""

    chunk_id: str
    document_id: str
    authority: str = UNKNOWN
    country: str = UNKNOWN
    document_type: str = UNKNOWN
    regulation_family: str = UNKNOWN
    regulation: str = UNKNOWN
    title: str = UNKNOWN
    part: str = UNKNOWN
    subpart: str = UNKNOWN
    section: str = UNKNOWN
    paragraph: str = UNKNOWN
    topic: str = UNKNOWN
    gxp_area: str = UNKNOWN
    compliance_domain: str = UNKNOWN
    chunk_type: str = "regulatory_requirement"
    effective_date: str = UNKNOWN
    version: str = UNKNOWN
    status: str = UNKNOWN
    source_url: str = UNKNOWN
    sequence: int = 1

    def __post_init__(self) -> None:
        if self.chunk_type not in CHUNK_TYPES:
            raise ValueError(
                f"chunk_type '{self.chunk_type}' is not one of the supported "
                f"types: {CHUNK_TYPES}"
            )

    @property
    def citation(self) -> Citation:
        return Citation(
            authority=self.authority,
            regulation=self.regulation,
            section=self.section,
            paragraph=self.paragraph,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Canonical nested representation, e.g. for API responses."""
        data = asdict(self)
        data["citation"] = self.citation.as_dict()
        return data

    def to_chroma_metadata(self) -> Dict[str, Any]:
        """
        Flattened representation safe for ChromaDB, which only accepts
        str/int/float/bool metadata values (no nested dicts). The citation
        is included as a single formatted string; every field it's built
        from (authority/regulation/section/paragraph) is still present at
        the top level for `where` filtering.
        """
        data = asdict(self)
        data["citation_path"] = self.citation.path()
        return data
