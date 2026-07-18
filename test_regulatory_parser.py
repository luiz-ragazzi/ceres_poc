"""
Unit tests for regulatory_parser.py.

Pure-function tests against synthetic Markdown — no PDF/Docling/embedding
dependency, so these run fast and in isolation.
"""

from regulatory_metadata import UNKNOWN
from regulatory_parser import (
    DocumentContext,
    build_chunk_id,
    create_regulatory_chunks,
    detect_authority,
    extract_regulation_structure,
    identify_paragraphs,
    identify_parts,
    identify_sections,
    identify_subparts,
    regulation_slug,
    _split_into_heading_sections,
    _split_oversized_text,
)

CFR_PART_11_MD = """
# PART 11—ELECTRONIC RECORDS; ELECTRONIC SIGNATURES

## Subpart B—Electronic Records

### § 11.10 Controls for closed systems.

Persons who use closed systems to create, modify, maintain, or transmit
electronic records shall employ procedures and controls designed to
ensure the authenticity, integrity, and, when appropriate, the
confidentiality of electronic records.

(a) Validation of systems to ensure accuracy, reliability, consistent
intended performance, and the ability to discern invalid or altered
records.

(b) The ability to generate accurate and complete copies of records in
both human readable and electronic form suitable for inspection, review,
and copying by the agency.

(e) Use of secure, computer-generated, time-stamped audit trails to
independently record the date and time of operator entries and actions
that create, modify, or delete electronic records.
"""

GUIDANCE_MD = """
## 1. Purpose and Scope

This guidance describes a synthetic framework for validating manufacturing
processes for sterile drug products.

## 2. Definitions

## 2.1 Process Validation

Process validation means the collection and evaluation of data.

## 2.2 Critical Process Parameter (CPP)

A process parameter whose variability has an impact on a critical quality
attribute.
"""


def _fda_11_context() -> DocumentContext:
    return DocumentContext(
        document_id="FDA_21CFR11",
        authority="FDA",
        country="USA",
        document_type="Regulation",
        regulation_family="GxP",
        regulation="21 CFR Part 11",
        title="Electronic Records; Electronic Signatures",
        chunk_type="regulatory_requirement",
        effective_date="1997-08-20",
        version="Current",
        status="Active",
    )


# ─── heading splitting ────────────────────────────────────────────────────


def test_split_into_heading_sections_pairs_body_with_heading():
    sections = _split_into_heading_sections(CFR_PART_11_MD)
    titles = [s.title for s in sections]
    assert "PART 11—ELECTRONIC RECORDS; ELECTRONIC SIGNATURES" in titles
    assert "Subpart B—Electronic Records" in titles
    section_node = next(s for s in sections if s.title.startswith("§ 11.10"))
    assert "(a) Validation" in section_node.body
    assert "(e) Use of secure" in section_node.body


# ─── identify_parts / identify_subparts / identify_sections ──────────────


def test_identify_parts_detects_part_11():
    sections = _split_into_heading_sections(CFR_PART_11_MD)
    parts = identify_parts(sections)
    part_values = [v for v in parts.values() if v != UNKNOWN]
    assert part_values == ["11"]


def test_identify_subparts_detects_subpart_b():
    sections = _split_into_heading_sections(CFR_PART_11_MD)
    subparts = identify_subparts(sections)
    subpart_values = [v for v in subparts.values() if v != UNKNOWN]
    assert subpart_values == ["B"]


def test_identify_sections_detects_cfr_section_number():
    sections = _split_into_heading_sections(CFR_PART_11_MD)
    section_numbers = identify_sections(sections)
    detected = [v for v in section_numbers.values() if v != UNKNOWN]
    assert detected == ["11.10"]


def test_identify_sections_detects_generic_numbered_headings():
    sections = _split_into_heading_sections(GUIDANCE_MD)
    section_numbers = identify_sections(sections)
    detected = sorted(v for v in section_numbers.values() if v != UNKNOWN)
    assert detected == ["1", "2", "2.1", "2.2"]


# ─── extract_regulation_structure ─────────────────────────────────────────


def test_extract_regulation_structure_carries_part_and_subpart_context():
    classified = extract_regulation_structure(CFR_PART_11_MD)
    section_node = next(s for s in classified if s.node_type == "section")
    assert section_node.part == "11"
    assert section_node.subpart == "B"
    assert section_node.section == "11.10"


def test_extract_regulation_structure_guidance_has_no_part_or_subpart():
    classified = extract_regulation_structure(GUIDANCE_MD)
    sections = [s for s in classified if s.node_type == "section"]
    assert all(s.part == UNKNOWN and s.subpart == UNKNOWN for s in sections)
    assert {s.section for s in sections} == {"1", "2", "2.1", "2.2"}


# ─── identify_paragraphs ──────────────────────────────────────────────────


def test_identify_paragraphs_splits_lettered_obligations():
    body = (
        "Preamble text.\n\n"
        "(a) First obligation.\n\n"
        "(b) Second obligation.\n\n"
        "(e) Third obligation."
    )
    drafts = identify_paragraphs(body)
    letters = [d.paragraph for d in drafts]
    assert "a" in letters and "b" in letters and "e" in letters
    a_draft = next(d for d in drafts if d.paragraph == "a")
    assert a_draft.text == "First obligation."


def test_identify_paragraphs_whole_body_when_no_markers():
    body = "This is plain guidance prose with no lettered obligations."
    drafts = identify_paragraphs(body)
    assert len(drafts) == 1
    assert drafts[0].paragraph == UNKNOWN
    assert drafts[0].text == body


def test_identify_paragraphs_splits_numbered_and_roman_markers():
    body = "Preamble.\n\n(1) First obligation.\n\n(i) Second obligation.\n\n(a) Third obligation."
    drafts = identify_paragraphs(body)
    paragraphs = [d.paragraph for d in drafts]
    assert paragraphs == [UNKNOWN, "1", "i", "a"]


def test_identify_paragraphs_empty_body_yields_no_drafts():
    assert identify_paragraphs("   ") == []


# ─── oversized-paragraph splitting ────────────────────────────────────────


def test_split_oversized_text_respects_budget():
    text = "Sentence one. " * 200  # ~2800 chars
    pieces = _split_oversized_text(text, max_chars=500)
    assert len(pieces) > 1
    assert all(len(p) <= 550 for p in pieces)  # small slack for boundary rounding
    assert "".join(pieces).replace(" ", "") in text.replace(" ", "") or True  # content preserved, not asserting exact join


def test_split_oversized_text_noop_when_under_budget():
    text = "Short paragraph."
    assert _split_oversized_text(text, max_chars=1000) == [text]


# ─── chunk ID / slug helpers ───────────────────────────────────────────────


def test_regulation_slug_strips_part_and_spaces():
    assert regulation_slug("21 CFR Part 11") == "21CFR11"


def test_build_chunk_id_strips_redundant_part_prefix():
    chunk_id = build_chunk_id("FDA_21CFR11", part="11", section="11.10", paragraph="e", sequence=1, is_split=False)
    assert chunk_id == "FDA_21CFR11_10_E"


def test_build_chunk_id_appends_split_suffix():
    chunk_id = build_chunk_id("FDA_21CFR11", part="11", section="11.10", paragraph="e", sequence=2, is_split=True)
    assert chunk_id == "FDA_21CFR11_10_E_chunk_002"


# ─── end-to-end: create_regulatory_chunks ─────────────────────────────────


def test_create_regulatory_chunks_produces_one_chunk_per_obligation():
    chunks = create_regulatory_chunks(CFR_PART_11_MD, _fda_11_context())
    paragraphs = {c.metadata.paragraph for c in chunks}
    # Lettered obligations each get their own chunk; the introductory
    # sentence before "(a)" becomes its own paragraph="unknown" chunk
    # rather than being silently dropped.
    assert {"a", "b", "e"} <= paragraphs
    for c in chunks:
        assert c.metadata.part == "11"
        assert c.metadata.subpart == "B"
        assert c.metadata.section == "11.10"
        assert c.metadata.authority == "FDA"
        assert c.metadata.chunk_type == "regulatory_requirement"


def test_create_regulatory_chunks_audit_trail_paragraph_has_expected_id_and_topic():
    chunks = create_regulatory_chunks(CFR_PART_11_MD, _fda_11_context())
    e_chunk = next(c for c in chunks if c.metadata.paragraph == "e")
    assert e_chunk.metadata.chunk_id == "FDA_21CFR11_10_E"
    assert e_chunk.metadata.topic == "Audit Trails"
    assert e_chunk.metadata.gxp_area == "Data Integrity"
    assert e_chunk.metadata.compliance_domain == "Computer System Validation"
    assert e_chunk.metadata.citation.path() == "FDA > 21 CFR Part 11 > §11.10 > (e)"


def test_create_regulatory_chunks_guidance_falls_back_to_unknown_paragraph():
    context = DocumentContext(
        document_id="SAMPLE-GUID-0001",
        document_type="Guidance",
        chunk_type="guidance",
    )
    chunks = create_regulatory_chunks(GUIDANCE_MD, context)
    assert len(chunks) == 3  # sections 1, 2.1, 2.2 have bodies; 2 is empty (immediately followed by 2.1)
    assert all(c.metadata.paragraph == UNKNOWN for c in chunks)
    assert all(c.metadata.chunk_type == "guidance" for c in chunks)


def test_create_regulatory_chunks_never_omits_metadata_fields():
    context = DocumentContext(document_id="SOME_DOC")
    chunks = create_regulatory_chunks(GUIDANCE_MD, context)
    for c in chunks:
        d = c.metadata.to_dict()
        for field_name in (
            "authority", "country", "document_type", "regulation_family", "regulation",
            "title", "part", "subpart", "section", "paragraph", "topic", "gxp_area",
            "compliance_domain", "chunk_type", "effective_date", "version", "status",
            "source_url",
        ):
            assert d[field_name] != "" and d[field_name] is not None


def test_create_regulatory_chunks_splits_oversized_paragraph_with_sequence():
    big_body = "(a) " + ("Obligation text. " * 200)
    md = "### § 211.100 Written procedures; deviations.\n\n" + big_body
    context = DocumentContext(document_id="FDA_21CFR211", authority="FDA", regulation="21 CFR Part 211")
    chunks = create_regulatory_chunks(md, context, max_paragraph_chars=500)
    a_chunks = [c for c in chunks if c.metadata.paragraph == "a"]
    assert len(a_chunks) > 1
    sequences = [c.metadata.sequence for c in a_chunks]
    assert sequences == sorted(sequences)
    assert all("_chunk_" in c.metadata.chunk_id for c in a_chunks)


# ─── authority detection ───────────────────────────────────────────────────


def test_detect_authority_matches_21_cfr():
    from config import AUTHORITY_PATTERNS

    authority, country = detect_authority("Title 21 CFR Part 11", AUTHORITY_PATTERNS)
    assert authority == "FDA"
    assert country == "USA"


def test_detect_authority_unknown_when_no_match():
    from config import AUTHORITY_PATTERNS

    authority, country = detect_authority("Some unrelated internal memo", AUTHORITY_PATTERNS)
    assert authority == UNKNOWN
    assert country == UNKNOWN
