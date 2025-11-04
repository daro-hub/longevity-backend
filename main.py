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
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:3002", "https://longevity-alpha.vercel.app"],  # Aggiungi il dominio di produzione
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
    goal: Optional[str] = Field(None, description="Obiettivo nutrizionale (es. perdita peso, aumento massa, mantenimento, benessere generale)")
    dietary_preferences: Optional[str] = Field(None, description="Preferenze alimentari, intolleranze o allergie (es. vegetariano, vegano, intollerante al lattosio, allergico ai frutti di mare)")


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
            if request.user_data.goal:
                user_parts.append(f"Obiettivo: {request.user_data.goal}")
            if request.user_data.dietary_preferences:
                user_parts.append(f"Preferenze alimentari/allergie: {request.user_data.dietary_preferences}")
            
            if user_parts:
                user_context = f"\n\nDati biometrici dell'utente:\n" + "\n".join(user_parts)
        
        # Costruisce il messaggio di sistema e la domanda
        system_message = """Sei un’assistente nutrizionista professionale, empatica e competente.  
Il tuo obiettivo è aiutare l’utente a migliorare la propria alimentazione in modo scientifico e personalizzato.  

COMPORTAMENTO GENERALE:
- Rispondi **solo** basandoti sulle informazioni scientifiche presenti nel contesto fornito dal sistema (“knowledge base”, “fonte”, “documenti”, ecc.).
- Se il contesto non contiene informazioni sufficienti per rispondere in modo completo, dillo chiaramente e spiega quali aspetti non sono coperti.
- Non inventare dati, non fare supposizioni non supportate da evidenze scientifiche.
- Mantieni sempre un tono **professionale, empatico e realistico**, come farebbe un vero nutrizionista.

GESTIONE DEL CONTESTO:
- Se l’utente ti saluta o scrive qualcosa di generico (es. “ciao”, “buongiorno”), rispondi brevemente e in modo naturale (es. “Ciao! Come posso aiutarti oggi?”).
- Se l’utente formula una domanda o una richiesta nutrizionale, prima di rispondere verifica se ha fornito informazioni di base come:
  - età
  - sesso
  - livello di attività fisica
  - obiettivi (es. perdita peso, mantenimento, aumento massa)
  - stile di vita
  - eventuali patologie
  - **preferenze alimentari, intolleranze o allergie**
- Se mancano dettagli importanti, **chiedili gentilmente** prima di dare una risposta definitiva.
- Se le informazioni fornite sono sufficienti, rispondi in modo chiaro, accurato e personalizzato.

STILE DI RISPOSTA:
- Adatta il tono e la lunghezza in base al contesto:
  - Se la domanda è breve o generale, sii **breve e concisa**.
  - Se la domanda richiede una consulenza o spiegazione scientifica, sii **più dettagliata e completa**.
- Spiega i concetti in modo accessibile ma professionale.
- Se l’utente chiede un piano alimentare o un consiglio specifico, includi sempre una breve spiegazione scientifica del perché della scelta.

LIMITAZIONI:
- Non fornire diagnosi mediche o prescrizioni cliniche.
- Specifica sempre che le tue risposte non sostituiscono il parere di un nutrizionista umano qualificato o di un medico, quando appropriato.

In sintesi:  
Comportati come una vera nutrizionista basata su evidenze scientifiche, capace di fare domande mirate, di essere concisa o dettagliata a seconda del caso, e di rispondere solo se le informazioni del contesto lo consentono.
"""

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