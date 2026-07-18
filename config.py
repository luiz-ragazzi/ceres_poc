"""
Configuration and constants for the compliance document RAG application.
"""

CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "pdf_chunks"

# Original PDFs + converted Markdown live here, independent of Chroma, so
# they survive a vector index rebuild or wipe.
DOCUMENTS_PATH = "./documents"
REGISTRY_DB_PATH = "./documents/registry.db"

EMBED_MODEL = "all-MiniLM-L6-v2"   # fast, good quality, ~80MB, runs locally
MAX_CHUNK_TOKENS = 256             # matches EMBED_MODEL's max sequence length

# ─── Regulatory structure-based chunking ───────────────────────────────────

# Upload-form doc_type -> (document_type, chunk_type) metadata mapping.
# chunk_type must be one of CHUNK_TYPES below; it drives compliance filtering
# (where={"chunk_type": "capa"}), so every DOC_TYPES entry must map to a
# valid chunk_type even when the mapping is a best-effort default.
DOC_TYPE_METADATA = {
    "Regulation": ("Regulation", "regulatory_requirement"),
    "Guidance": ("Guidance", "guidance"),
    "SOP": ("SOP", "sop"),
    "CAPA": ("CAPA", "capa"),
    "Validation Evidence": ("Validation Evidence", "validation_evidence"),
    "Risk Assessment": ("Risk Assessment", "risk_assessment"),
    "Deviation": ("Deviation", "deviation"),
    "Training Record": ("Training Record", "training_record"),
    "Other": ("unknown", "guidance"),
}
DOC_TYPES = list(DOC_TYPE_METADATA.keys())

# Chunk types the platform recognizes across all future document classes
# (regulations today; SOPs, CAPAs, validation evidence, etc. in later
# phases). Every chunk's "chunk_type" metadata field must be one of these.
CHUNK_TYPES = [
    "regulatory_requirement",
    "guidance",
    "sop",
    "validation_evidence",
    "capa",
    "risk_assessment",
    "deviation",
    "training_record",
]

# Regex (case-insensitive) -> (authority, country), checked in order against
# document title/filename/text to auto-detect the issuing authority when the
# uploader doesn't supply one explicitly. First match wins.
AUTHORITY_PATTERNS = [
    (r"21\s*CFR", "FDA", "USA"),
    (r"\bFDA\b", "FDA", "USA"),
    (r"EudraLex|EU[\s-]*GMP|European Medicines Agency|\bEMA\b|\bAnnex\s+1[15]\b", "EMA", "EU"),
    (r"\bICH\b", "ICH", "International"),
    (r"Swissmedic", "Swissmedic", "Switzerland"),
]

# Character budget for a single requirement-level chunk before it gets
# split (requirement #4). Sized well under MAX_CHUNK_TOKENS so the
# embedding model never has to silently truncate a chunk.
MAX_PARAGRAPH_CHARS = 1000

# Keyword -> category lookups used to enrich chunks with topic / gxp_area /
# compliance_domain metadata. Matched case-insensitively against the
# section heading + body text; first category with a keyword hit wins.
# Anything left unmatched is stored as "unknown" — metadata is never
# omitted, per requirement #6.
TOPIC_KEYWORDS = {
    "Audit Trails": ["audit trail"],
    "Electronic Signatures": ["electronic signature", "digital signature"],
    "Electronic Records": ["electronic record"],
    "Personnel Training": ["training", "personnel qualification"],
    "Validation Requirements": ["validation", "qualification", "media fill", "ppq"],
    "Security Controls": ["access control", "security control", "system security"],
    "Change Control": ["change control", "change request"],
    "Deviation Management": ["deviation", "capa", "corrective action", "investigation"],
    "Risk Assessment": ["risk assessment", "risk management", "fmea"],
    "Environmental Monitoring": ["environmental monitoring", "viable particulate", "clean area"],
    "Documentation": ["documentation", "record retention", "recordkeeping"],
}

GXP_AREA_KEYWORDS = {
    "Data Integrity": ["audit trail", "electronic signature", "electronic record", "data integrity"],
    "Personnel": ["training", "personnel", "gowning"],
    "Facilities & Equipment": ["facility", "equipment", "cleanroom", "clean area", "hvac", "utilities"],
    "Production": ["manufacturing", "batch record", "production", "process parameter"],
    "Quality Control": ["testing", "sampling", "laboratory", "specification", "quality control"],
    "Validation": ["validation", "qualification", "ppq", "media fill"],
    "Documentation": ["documentation", "record retention", "recordkeeping"],
    "Change Management": ["change control", "change request"],
    "Deviation Management": ["deviation", "capa", "corrective action", "investigation"],
}

COMPLIANCE_DOMAIN_KEYWORDS = {
    "Computer System Validation": ["electronic record", "electronic signature", "audit trail", "computer system", "software validation"],
    "Good Manufacturing Practice": ["manufacturing", "gmp", "batch", "production"],
    "Good Clinical Practice": ["clinical trial", "investigator", "informed consent"],
    "Good Laboratory Practice": ["laboratory", "analytical method"],
    "Quality Risk Management": ["risk assessment", "risk management", "fmea"],
    "Pharmacovigilance": ["adverse event", "pharmacovigilance", "safety signal"],
}

# HARD REQUIREMENT: this application must stay fully on-premises. Documents
# are regulated content (SOPs, CTDs, CAPA records, audit reports) that must
# never leave local infrastructure. OLLAMA_HOST must remain a local/on-prem
# inference endpoint — do NOT point this at a cloud API (Azure AI Foundry,
# OpenAI, Anthropic, etc.), including hosted "OpenAI-compatible" endpoints.
# If a Microsoft-branded runtime is ever wanted, use "Foundry Local" (an
# on-device runtime), never the Azure AI Foundry cloud service.
OLLAMA_HOST = "http://127.0.0.1:11434"
OLLAMA_MODEL = "llama3.2:latest"
OLLAMA_TIMEOUT = 120   # seconds

CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",   # Vite's actual default dev port
    "http://127.0.0.1:5173",
]
