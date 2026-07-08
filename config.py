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

DOC_TYPES = ["SOP", "CTD", "CAPA", "Audit Report", "Guidance Document", "Other"]

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
