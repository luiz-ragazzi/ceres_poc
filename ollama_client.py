"""
Answer synthesis via a local Ollama model, grounded in retrieved chunks.
"""

from typing import List

import requests

from config import OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_TIMEOUT
from models import QueryResult

SYSTEM_PROMPT = (
    "You are a compliance assistant answering questions about regulated documents "
    "(SOPs, CTDs, CAPA records, audit reports). Answer ONLY using the numbered "
    "excerpts provided below — never use outside knowledge. Cite the excerpt "
    "number(s) you relied on for every claim, like [1] or [2][3]. If the excerpts "
    "do not contain enough information to answer, say so explicitly instead of "
    "guessing."
)


class OllamaUnavailableError(Exception):
    """Raised when the local Ollama server can't be reached or errors out."""


def _build_context_block(chunks: List[QueryResult]) -> str:
    parts = []
    for i, c in enumerate(chunks, start=1):
        location = c.source
        if c.section_path:
            location += f" | Section: {c.section_path}"
        if c.pages:
            location += f" | Page(s): {c.pages}"
        parts.append(f"[{i}] Source: {location}\n{c.chunk}")
    return "\n\n".join(parts)


def generate_answer(question: str, chunks: List[QueryResult]) -> str:
    """Call the local Ollama model to synthesize a grounded answer from chunks."""
    context = _build_context_block(chunks)
    user_prompt = f"Excerpts:\n\n{context}\n\nQuestion: {question}"

    try:
        response = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
            },
            timeout=OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise OllamaUnavailableError(f"Could not reach Ollama at {OLLAMA_HOST}: {e}") from e

    return response.json()["message"]["content"]
