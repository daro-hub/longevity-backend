"""POST /v1/ask -- the retrieval-honest replacement for the legacy /ask.

Differences from /ask, all deliberate:
  - top_k=8, keeping the top 4 above a similarity threshold, instead of
    always trusting the nearest 3 regardless of relevance.
  - below threshold, the LLM is never called at all: a deterministic,
    bilingual "not in my sources" message is returned instantly. This is
    what makes "I don't know" reachable, and it's free.
  - numbered citations (doc, page, score, snippet) returned as structured
    data, not embedded in prose the model could misremember.
  - the model may only emit [n] markers pointing at supplied context; any
    marker outside that range is stripped server-side before the answer
    is returned (app.rag.citations.strip_invalid_markers).

Kept as a separate versioned route rather than modifying /ask in place so
the existing frontend integration keeps working unmodified until it
switches over (see the project plan's phased rollout).
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app import clients
from app.config import get_settings
from app.domain.messages import DISCLAIMER, NOT_IN_SOURCES
from app.rag.citations import build_citations, build_context_blocks, strip_invalid_markers
from app.rag.retrieve import query_vector_for_text, retrieve

router = APIRouter()
logger = logging.getLogger("app.api.ask_v1")

SYSTEM_MESSAGE_IT = """Sei un'assistente nutrizionista che risponde SOLO sulla base del contesto numerato fornito.
Regole:
- Puoi citare una fonte scrivendo esclusivamente il suo indice tra parentesi quadre, es. [1]. Non scrivere mai il nome del documento o il numero di pagina: verranno mostrati automaticamente dal sistema.
- Non inventare informazioni non presenti nel contesto.
- Se il contesto non è sufficiente per una parte della domanda, dillo esplicitamente.
- Non fornire diagnosi mediche; specifica che le risposte non sostituiscono un professionista qualificato quando appropriato."""

SYSTEM_MESSAGE_EN = """You are a nutrition assistant who answers ONLY based on the numbered context provided.
Rules:
- You may cite a source by writing only its index in square brackets, e.g. [1]. Never write the document name or page number yourself -- the system displays those automatically.
- Never invent information not present in the context.
- If the context is insufficient for part of the question, say so explicitly.
- Do not provide medical diagnoses; note that answers don't replace a qualified professional when appropriate."""


class AskV1Request(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    locale: str = Field("it", pattern="^(it|en)$")


class AskV1Response(BaseModel):
    answer: str
    grounded: bool
    citations: list[dict]
    disclaimer: str


@router.post("/v1/ask", response_model=AskV1Response)
async def ask_v1(request: Request, body: AskV1Request) -> AskV1Response:
    settings = get_settings()
    req_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    disclaimer = DISCLAIMER.get(body.locale, DISCLAIMER["it"])

    missing = settings.missing_required_for_ask()
    if missing:
        logger.error("ask_v1.not_configured", extra={"missing": missing, "request_id": req_id})
        raise HTTPException(status_code=503, detail=f"Service not configured (request_id={req_id})")

    try:
        openai_client = clients.get_openai_client()
        index = clients.get_pinecone_index()

        query_vector = query_vector_for_text(
            openai_client,
            body.question,
            settings.openai_embedding_model,
            settings.openai_embedding_dimensions,
        )
        chunks = retrieve(index, query_vector, namespace=settings.pinecone_namespace)

        if not chunks:
            return AskV1Response(
                answer=NOT_IN_SOURCES.get(body.locale, NOT_IN_SOURCES["it"]),
                grounded=False,
                citations=[],
                disclaimer=disclaimer,
            )

        context = build_context_blocks(chunks)
        citations = build_citations(chunks)
        system_message = SYSTEM_MESSAGE_EN if body.locale == "en" else SYSTEM_MESSAGE_IT

        completion = openai_client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=[
                {"role": "system", "content": system_message},
                {
                    "role": "user",
                    "content": f"Contesto:\n\n{context}\n\nDomanda: {body.question}",
                },
            ],
            temperature=0.3,
            max_tokens=1000,
        )
        answer = completion.choices[0].message.content
        if not answer:
            logger.warning("ask_v1.empty_completion", extra={"request_id": req_id})
            raise HTTPException(status_code=502, detail=f"Empty model response (request_id={req_id})")

        answer = strip_invalid_markers(answer, num_citations=len(citations))

        return AskV1Response(answer=answer, grounded=True, citations=citations, disclaimer=disclaimer)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("ask_v1.unhandled_error", extra={"request_id": req_id})
        raise HTTPException(
            status_code=500, detail=f"Internal server error (request_id={req_id})"
        ) from e
