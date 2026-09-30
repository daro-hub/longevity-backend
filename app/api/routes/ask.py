"""The legacy /ask endpoint, ported as-is from the original main.py with
Phase 0 fixes only (error handling, logging, no import-time crash). This
endpoint is deliberately NOT changed in retrieval behavior yet (still
top_k=3, no similarity threshold, no citations) — that's Phase 2 of the
project plan, which lands as a separate /v1/ask route so this one keeps
working unmodified until the frontend has moved over. It will be deleted
once /v1/ask is live.

Fixes applied here vs. the original:
  - The 404 "no relevant document" HTTPException used to be re-caught by
    the blanket `except Exception` (which saw `hasattr(e, 'status_code')`
    and re-raised it mislabeled as "Errore API OpenAI: 404: ..."). It's now
    re-raised as-is via a dedicated `except HTTPException: raise` before
    the generic handler runs.
  - Internal exception text is no longer forwarded to the client. It's
    logged server-side with a request id; the client gets a generic
    message plus that id.
  - `if request.user_data.age:` (etc.) silently dropped a legitimate `0`
    because falsy-vs-present was conflated. Fixed to `is not None`.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app import clients
from app.config import get_settings

router = APIRouter()
logger = logging.getLogger("app.api.ask")


class UserData(BaseModel):
    age: int | None = Field(None, ge=0, le=150)
    weight: float | None = Field(None, ge=0)
    height: float | None = Field(None, ge=0)
    gender: str | None = None
    activity_level: str | None = None
    goal: str | None = None
    dietary_preferences: str | None = None


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    user_data: UserData | None = None


class AskResponse(BaseModel):
    answer: str


SYSTEM_MESSAGE = """Sei un'assistente nutrizionista professionale, empatica e competente.
Il tuo obiettivo è aiutare l'utente a migliorare la propria alimentazione in modo scientifico e personalizzato.

COMPORTAMENTO GENERALE:
- Rispondi **solo** basandoti sulle informazioni scientifiche presenti nel contesto fornito dal sistema ("knowledge base", "fonte", "documenti", ecc.).
- Se il contesto non contiene informazioni sufficienti per rispondere in modo completo, dillo chiaramente e spiega quali aspetti non sono coperti.
- Non inventare dati, non fare supposizioni non supportate da evidenze scientifiche.
- Mantieni sempre un tono **professionale, empatico e realistico**, come farebbe un vero nutrizionista.

GESTIONE DEL CONTESTO:
- Se l'utente ti saluta o scrive qualcosa di generico (es. "ciao", "buongiorno"), rispondi brevemente e in modo naturale (es. "Ciao! Come posso aiutarti oggi?").
- Se l'utente formula una domanda o una richiesta nutrizionale, prima di rispondere verifica se ha fornito informazioni di base come età, sesso, livello di attività fisica, obiettivi, stile di vita, patologie, preferenze alimentari, intolleranze o allergie.
- Se mancano dettagli importanti, chiedili gentilmente prima di dare una risposta definitiva.
- Se le informazioni fornite sono sufficienti, rispondi in modo chiaro, accurato e personalizzato.

STILE DI RISPOSTA:
- Adatta il tono e la lunghezza in base al contesto: breve e concisa per domande generiche, più dettagliata per consulenze scientifiche.
- Spiega i concetti in modo accessibile ma professionale.

LIMITAZIONI:
- Non fornire diagnosi mediche o prescrizioni cliniche.
- Specifica sempre che le tue risposte non sostituiscono il parere di un nutrizionista umano qualificato o di un medico, quando appropriato.
"""


def _build_user_context(user_data: UserData | None) -> str:
    if not user_data:
        return ""
    parts = []
    if user_data.age is not None:
        parts.append(f"Età: {user_data.age} anni")
    if user_data.weight is not None:
        parts.append(f"Peso: {user_data.weight} kg")
    if user_data.height is not None:
        parts.append(f"Altezza: {user_data.height} cm")
    if user_data.gender:
        parts.append(f"Genere: {user_data.gender}")
    if user_data.activity_level:
        parts.append(f"Livello di attività: {user_data.activity_level}")
    if user_data.goal:
        parts.append(f"Obiettivo: {user_data.goal}")
    if user_data.dietary_preferences:
        parts.append(f"Preferenze alimentari/allergie: {user_data.dietary_preferences}")
    if not parts:
        return ""
    return "\n\nDati biometrici dell'utente:\n" + "\n".join(parts)


@router.post("/ask", response_model=AskResponse)
async def ask_question(request: Request, body: AskRequest) -> AskResponse:
    settings = get_settings()
    req_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    missing = settings.missing_required_for_ask()
    if missing:
        logger.error("ask.not_configured", extra={"missing": missing, "request_id": req_id})
        raise HTTPException(status_code=503, detail=f"Service not configured (request_id={req_id})")

    try:
        openai_client = clients.get_openai_client()
        index = clients.get_pinecone_index()

        embedding_response = openai_client.embeddings.create(
            model=settings.openai_embedding_model,
            input=body.question,
            dimensions=settings.openai_embedding_dimensions,
        )
        query_vector = embedding_response.data[0].embedding

        query_results = index.query(vector=query_vector, top_k=3, include_metadata=True)

        context_documents = []
        for match in query_results.matches:
            metadata = match.metadata or {}
            if "text" in metadata:
                context_documents.append(metadata["text"])
            elif "content" in metadata:
                context_documents.append(metadata["content"])

        if not context_documents:
            raise HTTPException(status_code=404, detail="Nessun documento rilevante trovato")

        context = "\n\n".join(context_documents)
        user_context = _build_user_context(body.user_data)

        user_message = f"""Contesto scientifico (fonte: database Pinecone):

{context}
{user_context}

Domanda dell'utente: {body.question}

Fornisci una risposta dettagliata basata esclusivamente sulle informazioni fornite nel contesto sopra."""

        completion = openai_client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=[
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
            max_tokens=1000,
        )

        answer = completion.choices[0].message.content
        if not answer:
            logger.warning("ask.empty_completion", extra={"request_id": req_id})
            raise HTTPException(status_code=502, detail=f"Empty model response (request_id={req_id})")

        return AskResponse(answer=answer)

    except HTTPException:
        raise  # deliberate passthrough — do NOT let the generic handler below re-wrap this
    except Exception as e:
        logger.exception("ask.unhandled_error", extra={"request_id": req_id})
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error (request_id={req_id})",
        ) from e
