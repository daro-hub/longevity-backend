"""Turns retrieved chunks into numbered context blocks for the prompt, and
back into a structured citations array for the API response.

The non-hallucinatable trick: the model is given numbered context blocks
and instructed to emit ONLY `[n]` markers pointing at them -- never
free-form citation text (page numbers it writes itself would be
invented). strip_invalid_markers is the server-side backstop: any `[n]`
the model emits where n is out of range gets removed rather than trusted.
"""

from __future__ import annotations

import re

from app.rag.retrieve import RetrievedChunk


def build_context_blocks(chunks: list[RetrievedChunk]) -> str:
    blocks = []
    for i, chunk in enumerate(chunks, start=1):
        blocks.append(f"[{i}] {chunk.text}")
    return "\n\n".join(blocks)


def build_citations(chunks: list[RetrievedChunk]) -> list[dict]:
    citations = []
    for i, chunk in enumerate(chunks, start=1):
        m = chunk.metadata
        page_start = m.get("page_start")
        page_end = m.get("page_end")
        page = str(page_start) if page_start == page_end else f"{page_start}-{page_end}"
        citations.append(
            {
                "n": i,
                "doc_id": m.get("doc_id"),
                "title": m.get("source_title"),
                "page": page,
                "score": round(chunk.score, 3),
                "snippet": chunk.text[:200],
                "url": m.get("url"),
            }
        )
    return citations


_MARKER_RE = re.compile(r"\[(\d+)\]")


def strip_invalid_markers(answer: str, num_citations: int) -> str:
    """Removes any [n] marker where n is not a valid citation index
    (1..num_citations). The model occasionally emits markers beyond what
    it was given, or references from a prior turn -- those never get
    surfaced as if they were real.
    """

    def replace(match: re.Match) -> str:
        n = int(match.group(1))
        if 1 <= n <= num_citations:
            return match.group(0)
        return ""

    return _MARKER_RE.sub(replace, answer)
