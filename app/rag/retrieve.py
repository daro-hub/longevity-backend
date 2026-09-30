"""Query-side retrieval: fetch top_k candidates, keep only the ones above
a similarity threshold. `top_k=3` with no threshold (the old /ask
behavior) always returns the 3 nearest vectors, relevant or not — this is
what makes "I don't know" reachable at all.

RETRIEVAL_MIN_SCORE in app.domain.references is a placeholder until
scripts/tune_threshold.py has run against this corpus with a real labeled
eval set (needs OPENAI_API_KEY + a populated Pinecone index — not
available yet in this environment). Treat the current value as
provisional; the mechanism below is what matters and is fully tested with
synthetic scores.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain import references as ref


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    metadata: dict
    score: float


def filter_by_threshold(
    matches: list,
    min_score: float = ref.RETRIEVAL_MIN_SCORE,
    keep_above_threshold: int = ref.RETRIEVAL_KEEP_ABOVE_THRESHOLD,
) -> list[RetrievedChunk]:
    """matches: objects with `.score` and `.metadata` (Pinecone's own
    QueryMatch shape, or any stand-in with those two attributes -- kept
    duck-typed so tests don't need to construct a real Pinecone object).
    Assumes matches arrive sorted by score descending (Pinecone's
    contract); does not re-sort.
    """
    kept: list[RetrievedChunk] = []
    for match in matches:
        if match.score < min_score:
            break  # sorted descending -- nothing after this clears the bar either
        metadata = match.metadata or {}
        text = metadata.get("text")
        if not text:
            continue
        kept.append(RetrievedChunk(text=text, metadata=metadata, score=match.score))
        if len(kept) >= keep_above_threshold:
            break
    return kept


def query_vector_for_text(openai_client, text: str, model: str, dimensions: int) -> list[float]:
    response = openai_client.embeddings.create(model=model, input=text, dimensions=dimensions)
    return response.data[0].embedding


def retrieve(
    index,
    query_vector: list[float],
    namespace: str = "",
    top_k: int = ref.RETRIEVAL_TOP_K,
    min_score: float = ref.RETRIEVAL_MIN_SCORE,
    keep_above_threshold: int = ref.RETRIEVAL_KEEP_ABOVE_THRESHOLD,
) -> list[RetrievedChunk]:
    results = index.query(
        vector=query_vector, top_k=top_k, include_metadata=True, namespace=namespace
    )
    return filter_by_threshold(results.matches, min_score, keep_above_threshold)
