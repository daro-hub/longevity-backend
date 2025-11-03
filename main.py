from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
import os
from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone

# Carica le variabili d'ambiente
load_dotenv()

# Inizializza FastAPI
app = FastAPI(
    title="longevity Backend",
    description="Backend API per consulenze nutrizionali basate su AI",
    version="1.0.0"
)

# Configurazione CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:3002", "https://tuodominio.com"],  # Aggiungi il dominio di produzione
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurazione OpenAI
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise ValueError("OPENAI_API_KEY non trovata nelle variabili d'ambiente")

# Inizializza il client OpenAI
openai_client = OpenAI(api_key=openai_api_key)

# Configurazione Pinecone
pinecone_api_key = os.getenv("PINECONE_API_KEY")
pinecone_index_name = os.getenv("PINECONE_INDEX_NAME")

if not pinecone_api_key or not pinecone_index_name:
    raise ValueError("Variabili d'ambiente Pinecone mancanti")

# Inizializza Pinecone
pc = Pinecone(api_key=pinecone_api_key)

# Modelli Pydantic per la validazione
class UserData(BaseModel):
    age: Optional[int] = Field(None, ge=0, le=150, description="Età dell'utente")
    weight: Optional[float] = Field(None, ge=0, description="Peso in kg")
    height: Optional[float] = Field(None, ge=0, description="Altezza in cm")
    gender: Optional[str] = Field(None, description="Genere")
    activity_level: Optional[str] = Field(None, description="Livello di attività fisica")


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Domanda dell'utente")
    user_data: Optional[UserData] = Field(None, description="Dati biometrici dell'utente")


class AskResponse(BaseModel):
    answer: str = Field(..., description="Risposta generata da GPT-4")


@app.get("/")
async def root():
    """Endpoint di health check"""
    return {"status": "ok", "message": "longevity Backend è attivo"}


@app.post("/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    """
    Endpoint principale per fare domande nutrizionali.
    
    Riceve una domanda e opzionalmente dati biometrici,
    interroga Pinecone per documenti rilevanti,
    e genera una risposta usando GPT-4.
    """
    try:
        # Recupera l'indice Pinecone
        index = pc.Index(pinecone_index_name)
        
        # Crea l'embedding della domanda usando OpenAI
        # Usa text-embedding-3-small con dimensions=1024 per compatibilità con l'indice Pinecone
        embedding_response = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=request.question,
            dimensions=1024
        )
        query_vector = embedding_response.data[0].embedding
        
        # Query su Pinecone per recuperare i top 3 documenti più rilevanti
        query_results = index.query(
            vector=query_vector,
            top_k=3,
            include_metadata=True
        )
        
        # Estrae i testi dai documenti recuperati
        context_documents = []
        for match in query_results.matches:
            if match.metadata and 'text' in match.metadata:
                context_documents.append(match.metadata['text'])
            elif 'content' in match.metadata:
                context_documents.append(match.metadata['content'])
        
        if not context_documents:
            raise HTTPException(
                status_code=404,
                detail="Nessun documento rilevante trovato in Pinecone"
            )
        
        # Costruisce il contesto per GPT-4
        context = "\n\n".join(context_documents)
        
        # Prepara il prompt con i dati biometrici se presenti
        user_context = ""
        if request.user_data:
            user_parts = []
            if request.user_data.age:
                user_parts.append(f"Età: {request.user_data.age} anni")
            if request.user_data.weight:
                user_parts.append(f"Peso: {request.user_data.weight} kg")
            if request.user_data.height:
                user_parts.append(f"Altezza: {request.user_data.height} cm")
            if request.user_data.gender:
                user_parts.append(f"Genere: {request.user_data.gender}")
            if request.user_data.activity_level:
                user_parts.append(f"Livello di attività: {request.user_data.activity_level}")
            
            if user_parts:
                user_context = f"\n\nDati biometrici dell'utente:\n" + "\n".join(user_parts)
        
        # Costruisce il messaggio di sistema e la domanda
        system_message = """Sei un assistente nutrizionale esperto. 
Rispondi SOLO basandoti sulle informazioni scientifiche fornite nel contesto.
Se le informazioni nel contesto non sono sufficienti per rispondere completamente, 
indica chiaramente quali aspetti non sono coperti dalle fonti disponibili.
Mantieni un tono professionale e basato su evidenze scientifiche."""

        user_message = f"""Contesto scientifico (fonte: database Pinecone):

{context}
{user_context}

Domanda dell'utente: {request.question}

Fornisci una risposta dettagliata basata esclusivamente sulle informazioni fornite nel contesto sopra."""

        # Chiama GPT-4 per generare la risposta
        completion = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        answer = completion.choices[0].message.content
        
        return AskResponse(answer=answer)
    
    except Exception as e:
        # Gestisce errori specifici di OpenAI se presenti
        if hasattr(e, 'status_code'):
            status_code = getattr(e, 'status_code', 500)
            raise HTTPException(
                status_code=status_code,
                detail=f"Errore API OpenAI: {str(e)}"
            )
        # Gestisce tutti gli altri errori
        raise HTTPException(
            status_code=500,
            detail=f"Errore interno del server: {str(e)}"
        )

