"""
Regulatory structure-based chunker.

Replaces generic fixed-size text splitting with a parser that understands
the shape of regulatory documents:

    Document -> Authority -> Regulation -> Part -> Subpart -> Section -> Paragraph

and produces one chunk per regulatory obligation (a lettered/numbered
paragraph, e.g. 21 CFR 11.10(e)) instead of one chunk per N tokens.

Input is Markdown text with heading markers (`#`, `##`, ...) — the output
of Docling's PDF-to-Markdown conversion in pdf_processor.py. Keeping this
module a pure function of markdown text (no PDF/Docling dependency) makes
it unit-testable in isolation.

Two document shapes are supported:

  * CFR-style regulations: "PART 11", "Subpart B", "§ 11.10", with
    lettered/numbered obligations like "(a)", "(1)", "(i)" inline in the
    section body.
  * Numbered guidance documents (ICH/EMA/FDA guidance, internal SOPs):
    headings like "4.2.1 Compression Force" with no explicit Part/Subpart
    or lettered sub-paragraphs. Each numbered heading becomes its own
    section-level chunk.

Sections with no recognizable numbering are dropped in only one case: an
empty body (nothing to embed). Everything else keeps its content, with
unresolved hierarchy fields set to "unknown" rather than silently discarded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List

from config import (
    COMPLIANCE_DOMAIN_KEYWORDS,
    GXP_AREA_KEYWORDS,
    MAX_PARAGRAPH_CHARS,
    TOPIC_KEYWORDS,
)
from regulatory_metadata import UNKNOWN, ChunkMetadata

# ─── Regex patterns for regulatory numbering ────────────────────────────────

_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*)$", re.MULTILINE)

_PART_RE = re.compile(r"^part\s+(\d+[a-z]?)\b[\s\-—:]*(.*)$", re.IGNORECASE)
_SUBPART_RE = re.compile(r"^subpart\s+([a-z])\b[\s\-—:]*(.*)$", re.IGNORECASE)

# CFR section: "§ 11.10", "§11.10", "Sec. 11.10", followed by an optional title.
_CFR_SECTION_RE = re.compile(r"^(?:§|sec\.?)\s*(\d+[a-z]?)\.(\d+[a-z]?)\b[\s\-—:]*(.*)$", re.IGNORECASE)
# Generic dotted numeric heading: "4.2.1 Compression Force", "1.1 Purpose".
_NUMERIC_SECTION_RE = re.compile(r"^(\d+(?:\.\d+)*)\b[\s\-—:.]*(.*)$")

# Top-level obligation markers, e.g. "(a) ...", "(1) ...", or "(i) ..."
# starting on their own line (Docling generally puts each on its own
# paragraph/line break).
_LETTERED_PARAGRAPH_RE = re.compile(r"(?:^|\n)\s*\(([a-z]+|\d+|[ivx]{1,3})\)\s+")


# ─── Data model ──────────────────────────────────────────────────────────────


@dataclass
class RawSection:
    """One markdown heading and the body text directly beneath it."""

    level: int
    title: str
    body: str


@dataclass
class ClassifiedSection:
    """A RawSection resolved to its place in the regulatory hierarchy."""

    node_type: str  # "part" | "subpart" | "section" | "other"
    title: str
    body: str
    part: str = UNKNOWN
    subpart: str = UNKNOWN
    section: str = UNKNOWN


@dataclass
class ChunkDraft:
    """A candidate chunk before size-based splitting and ID assignment."""

    text: str
    heading_title: str
    part: str = UNKNOWN
    subpart: str = UNKNOWN
    section: str = UNKNOWN
    paragraph: str = UNKNOWN


@dataclass
class RegulatoryChunk:
    """A finished, embeddable chunk with its full metadata attached."""

    text: str
    embed_text: str
    metadata: ChunkMetadata
    # The section heading this chunk was drawn from — not part of the
    # mandated metadata schema, but useful for callers (e.g. pdf_processor's
    # PDF-page lookup) that need to relate a chunk back to document structure
    # Docling parsed separately.
    heading_title: str = ""


# ─── Structure extraction ───────────────────────────────────────────────────


def _split_into_heading_sections(markdown_text: str) -> List[RawSection]:
    """Walk top-to-bottom, pairing each heading with the text until the next one."""
    matches = list(_HEADING_RE.finditer(markdown_text))
    sections: List[RawSection] = []
    for i, m in enumerate(matches):
        level = len(m.group(1))
        title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown_text)
        body = markdown_text[start:end].strip()
        sections.append(RawSection(level=level, title=title, body=body))
    return sections


def identify_parts(sections: List[RawSection]) -> Dict[int, str]:
    """Map each RawSection's index to a detected Part number, or UNKNOWN."""
    result: Dict[int, str] = {}
    for i, sec in enumerate(sections):
        m = _PART_RE.match(sec.title)
        result[i] = m.group(1).upper() if m else UNKNOWN
    return result


def identify_subparts(sections: List[RawSection]) -> Dict[int, str]:
    """Map each RawSection's index to a detected Subpart letter, or UNKNOWN."""
    result: Dict[int, str] = {}
    for i, sec in enumerate(sections):
        m = _SUBPART_RE.match(sec.title)
        result[i] = m.group(1).upper() if m else UNKNOWN
    return result


def identify_sections(sections: List[RawSection]) -> Dict[int, str]:
    """
    Map each RawSection's index to a detected Section number (e.g. "11.10"
    for CFR, "4.2.1" for a numbered guidance heading), or UNKNOWN.
    """
    result: Dict[int, str] = {}
    for i, sec in enumerate(sections):
        if _PART_RE.match(sec.title) or _SUBPART_RE.match(sec.title):
            result[i] = UNKNOWN
            continue
        cfr_m = _CFR_SECTION_RE.match(sec.title)
        if cfr_m:
            result[i] = f"{cfr_m.group(1)}.{cfr_m.group(2)}"
            continue
        num_m = _NUMERIC_SECTION_RE.match(sec.title)
        result[i] = num_m.group(1) if num_m else UNKNOWN
    return result


def extract_regulation_structure(markdown_text: str) -> List[ClassifiedSection]:
    """
    Parse markdown headings into a flat list of ClassifiedSections, carrying
    forward the most recent Part/Subpart context onto each Section (and
    resolving the "part" prefix out of dotted CFR section numbers, e.g. a
    "§ 11.10" found under "PART 11" keeps part="11", section="11.10").
    """
    raw_sections = _split_into_heading_sections(markdown_text)
    parts = identify_parts(raw_sections)
    subparts = identify_subparts(raw_sections)
    section_numbers = identify_sections(raw_sections)

    classified: List[ClassifiedSection] = []
    current_part = UNKNOWN
    current_subpart = UNKNOWN

    for i, sec in enumerate(raw_sections):
        if parts[i] != UNKNOWN:
            current_part = parts[i]
            current_subpart = UNKNOWN  # a new Part resets Subpart context
            classified.append(
                ClassifiedSection(node_type="part", title=sec.title, body=sec.body, part=current_part)
            )
            continue

        if subparts[i] != UNKNOWN:
            current_subpart = subparts[i]
            classified.append(
                ClassifiedSection(
                    node_type="subpart",
                    title=sec.title,
                    body=sec.body,
                    part=current_part,
                    subpart=current_subpart,
                )
            )
            continue

        if section_numbers[i] != UNKNOWN:
            classified.append(
                ClassifiedSection(
                    node_type="section",
                    title=sec.title,
                    body=sec.body,
                    part=current_part,
                    subpart=current_subpart,
                    section=section_numbers[i],
                )
            )
            continue

        classified.append(
            ClassifiedSection(
                node_type="other",
                title=sec.title,
                body=sec.body,
                part=current_part,
                subpart=current_subpart,
            )
        )

    return classified


# ─── Paragraph-level splitting ───────────────────────────────────────────────


def identify_paragraphs(body: str) -> List[ChunkDraft]:
    """
    Split a section body into single-obligation paragraphs using top-level
    lettered markers, e.g. "(a) ... (b) ... (c) ...". Nested numbered/roman
    sub-items ("(1)", "(i)") stay inside their parent lettered paragraph —
    they're rarely independent obligations on their own, and oversized
    paragraphs are still caught by the size-based splitter downstream.

    If no lettered markers are found, the whole body is returned as a
    single paragraph="unknown" draft (typical for guidance-style prose).
    """
    matches = list(_LETTERED_PARAGRAPH_RE.finditer(body))
    if not matches:
        return [ChunkDraft(text=body, heading_title="", paragraph=UNKNOWN)] if body.strip() else []

    drafts: List[ChunkDraft] = []
    preamble = body[: matches[0].start()].strip()
    if preamble:
        drafts.append(ChunkDraft(text=preamble, heading_title="", paragraph=UNKNOWN))

    for i, m in enumerate(matches):
        marker = m.group(1).lower()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        text = body[start:end].strip()
        if text:
            drafts.append(ChunkDraft(text=text, heading_title="", paragraph=marker))

    return drafts


def _split_oversized_text(text: str, max_chars: int) -> List[str]:
    """
    Break oversized text into <= max_chars pieces on sentence/paragraph
    boundaries where possible, falling back to a hard cut. Used only when a
    single obligation's text exceeds the embedding-friendly size budget.
    """
    if len(text) <= max_chars:
        return [text]

    pieces: List[str] = []
    remaining = text.strip()
    boundary_re = re.compile(r"(?<=[.!?])\s+|\n+")

    while len(remaining) > max_chars:
        window = remaining[:max_chars]
        boundaries = list(boundary_re.finditer(window))
        cut = boundaries[-1].end() if boundaries else max_chars
        pieces.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()

    if remaining:
        pieces.append(remaining)

    return [p for p in pieces if p]


# ─── Metadata enrichment ─────────────────────────────────────────────────────


def _keyword_lookup(text: str, keyword_map: Dict[str, List[str]]) -> str:
    lowered = text.lower()
    for category, keywords in keyword_map.items():
        if any(kw in lowered for kw in keywords):
            return category
    return UNKNOWN


def _infer_topic(heading_title: str, body: str) -> str:
    combined = f"{heading_title} {body}"
    topic = _keyword_lookup(combined, TOPIC_KEYWORDS)
    if topic != UNKNOWN:
        return topic
    # Fall back to the section's own heading — still determinable, just not
    # from the controlled vocabulary above.
    return heading_title.strip() or UNKNOWN


def _infer_gxp_area(heading_title: str, body: str) -> str:
    return _keyword_lookup(f"{heading_title} {body}", GXP_AREA_KEYWORDS)


def _infer_compliance_domain(heading_title: str, body: str) -> str:
    return _keyword_lookup(f"{heading_title} {body}", COMPLIANCE_DOMAIN_KEYWORDS)


# ─── Chunk ID assembly ────────────────────────────────────────────────────────


def _section_suffix(section: str, part: str) -> str:
    """
    Strip a redundant leading part-number from the section before slugging,
    so "part=11, section=11.10" contributes "10" (not "11_10") to the chunk
    ID — document_id already encodes the part via the regulation string.
    """
    if section == UNKNOWN:
        return "SEC-UNKNOWN"
    seg = section
    if part != UNKNOWN and seg.startswith(f"{part}."):
        seg = seg[len(part) + 1 :]
    return re.sub(r"[^A-Za-z0-9]+", "_", seg).strip("_") or "SEC-UNKNOWN"


def build_chunk_id(document_id: str, part: str, section: str, paragraph: str, sequence: int, is_split: bool) -> str:
    pieces = [document_id, _section_suffix(section, part)]
    if paragraph != UNKNOWN:
        pieces.append(paragraph.upper())
    chunk_id = "_".join(pieces)
    if is_split:
        chunk_id += f"_chunk_{sequence:03d}"
    return chunk_id


def regulation_slug(regulation: str) -> str:
    """'21 CFR Part 11' -> '21CFR11'."""
    if regulation == UNKNOWN:
        return UNKNOWN
    stripped = re.sub(r"\bpart\b", "", regulation, flags=re.IGNORECASE)
    return re.sub(r"[^A-Za-z0-9]+", "", stripped)


# ─── Top-level entry point ───────────────────────────────────────────────────


@dataclass
class DocumentContext:
    """Document-level facts supplied at upload time (or auto-detected)."""

    document_id: str
    authority: str = UNKNOWN
    country: str = UNKNOWN
    document_type: str = UNKNOWN
    regulation_family: str = UNKNOWN
    regulation: str = UNKNOWN
    title: str = UNKNOWN
    chunk_type: str = "regulatory_requirement"
    effective_date: str = UNKNOWN
    version: str = UNKNOWN
    status: str = UNKNOWN
    source_url: str = UNKNOWN


def create_regulatory_chunks(
    markdown_text: str,
    context: DocumentContext,
    max_paragraph_chars: int = MAX_PARAGRAPH_CHARS,
) -> List[RegulatoryChunk]:
    """
    Full pipeline: Markdown -> hierarchy extraction -> paragraph-level
    obligations -> size-bounded, fully-metadata'd chunks ready to embed.
    """
    classified_sections = extract_regulation_structure(markdown_text)
    chunks: List[RegulatoryChunk] = []

    for sec in classified_sections:
        if sec.node_type not in ("section", "other"):
            continue
        if not sec.body.strip():
            continue

        for draft in identify_paragraphs(sec.body):
            draft.heading_title = sec.title
            draft.part = sec.part
            draft.subpart = sec.subpart
            draft.section = sec.section

            pieces = _split_oversized_text(draft.text, max_paragraph_chars)
            is_split = len(pieces) > 1

            for seq, piece in enumerate(pieces, start=1):
                chunk_id = build_chunk_id(
                    context.document_id, draft.part, draft.section, draft.paragraph, seq, is_split
                )
                metadata = ChunkMetadata(
                    chunk_id=chunk_id,
                    document_id=context.document_id,
                    authority=context.authority,
                    country=context.country,
                    document_type=context.document_type,
                    regulation_family=context.regulation_family,
                    regulation=context.regulation,
                    title=context.title,
                    part=draft.part,
                    subpart=draft.subpart,
                    section=draft.section,
                    paragraph=draft.paragraph,
                    topic=_infer_topic(draft.heading_title, piece),
                    gxp_area=_infer_gxp_area(draft.heading_title, piece),
                    compliance_domain=_infer_compliance_domain(draft.heading_title, piece),
                    chunk_type=context.chunk_type,
                    effective_date=context.effective_date,
                    version=context.version,
                    status=context.status,
                    source_url=context.source_url,
                    sequence=seq,
                )
                embed_text = f"{draft.heading_title}\n{piece}" if draft.heading_title else piece
                chunks.append(
                    RegulatoryChunk(
                        text=piece, embed_text=embed_text, metadata=metadata, heading_title=draft.heading_title
                    )
                )

    return chunks


def detect_authority(text: str, patterns) -> tuple[str, str]:
    """Scan text against AUTHORITY_PATTERNS, returning (authority, country) or (unknown, unknown)."""
    for pattern, authority, country in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return authority, country
    return UNKNOWN, UNKNOWN
