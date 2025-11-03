# longevity Backend

Backend FastAPI per consulenze nutrizionali basate su AI. Il sistema utilizza Pinecone come database vettoriale per recuperare documenti scientifici rilevanti e GPT-4 per generare risposte nutrizionali basate esclusivamente sulle fonti presenti nel database.

## 🚀 Funzionalità

- Endpoint `/ask` per fare domande nutrizionali
- Supporto per dati biometrici opzionali (età, peso, altezza, ecc.)
- Ricerca semantica su Pinecone per documenti rilevanti
- Generazione risposte con GPT-4 basate solo su fonti scientifiche

## 📋 Requisiti

- Python 3.11+
- Account OpenAI con API key
- Account Pinecone con indice configurato
- Variabili d'ambiente configurate

## 🛠️ Installazione Locale

1. **Clona il repository e naviga nella directory:**

```bash
cd wellneAi-backend
```

2. **Crea un ambiente virtuale:**

```bash
python -m venv venv
```

3. **Attiva l'ambiente virtuale:**

**Windows:**
```bash
venv\Scripts\activate
```

**Linux/Mac:**
```bash
source venv/bin/activate
```

4. **Installa le dipendenze:**

```bash
pip install -r requirements.txt
```

5. **Configura le variabili d'ambiente:**

Copia il file `.env.example` e crea un file `.env`:

```bash
copy .env.example .env  # Windows
# oppure
cp .env.example .env    # Linux/Mac
```

Modifica il file `.env` con le tue chiavi API:

```env
OPENAI_API_KEY=your-openai-api-key
PINECONE_API_KEY=your-pinecone-api-key
PINECONE_ENVIRONMENT=us-east1-gcp
PINECONE_INDEX_NAME=nutri-ai-knowledge
```

## 🏃 Avvio Locale

Avvia il server di sviluppo:

```bash
uvicorn main:app --reload
```

Il server sarà disponibile su `http://localhost:8000`.

Puoi accedere alla documentazione interattiva su:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 📡 Utilizzo dell'Endpoint `/ask`

### Richiesta POST

Fai una richiesta POST a `http://localhost:8000/ask` con il seguente corpo JSON:

```json
{
  "question": "Qual è l'apporto giornaliero raccomandato di proteine per un adulto?",
  "user_data": {
    "age": 25,
    "weight": 70,
    "height": 180,
    "gender": "maschio",
    "activity_level": "moderato"
  }
}
```

**Nota:** Il campo `user_data` è opzionale. Puoi inviare solo la domanda:

```json
{
  "question": "Quali sono i benefici degli omega-3?"
}
```

### Risposta

La risposta sarà in formato JSON:

```json
{
  "answer": "Secondo le fonti scientifiche disponibili..."
}
```

### Esempio con cURL

```bash
curl -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Quante calorie dovrei assumere giornalmente?",
    "user_data": {
      "age": 30,
      "weight": 75,
      "height": 175
    }
  }'
```

### Esempio con Python

```python
import requests

url = "http://localhost:8000/ask"
payload = {
    "question": "Qual è l'importanza delle vitamine nel metabolismo?",
    "user_data": {
        "age": 28,
        "weight": 68,
        "height": 170
    }
}

response = requests.post(url, json=payload)
print(response.json())
```

## 🌐 Deploy su Render

### Configurazione

1. **Crea un nuovo Web Service su Render**

2. **Configura le variabili d'ambiente:**

Aggiungi le seguenti variabili d'ambiente nella sezione "Environment" di Render:

- `OPENAI_API_KEY`: La tua chiave API OpenAI
- `PINECONE_API_KEY`: La tua chiave API Pinecone
- `PINECONE_ENVIRONMENT`: Il tuo ambiente Pinecone (es. `us-east1-gcp`)
- `PINECONE_INDEX_NAME`: Il nome del tuo indice Pinecone (es. `nutri-ai-knowledge`)

3. **Configura il Build Command:**

```bash
pip install -r requirements.txt
```

4. **Configura il Start Command:**

```bash
gunicorn -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:$PORT
```

**Nota:** Render fornisce automaticamente la variabile `$PORT`, quindi usa quella invece di una porta fissa.

### Struttura del Progetto

Render si aspetta che il progetto abbia questa struttura:

```
wellneAi-backend/
├── main.py
├── requirements.txt
├── .env.example
└── README.md
```

## 🔧 Struttura del Codice

- `main.py`: Contiene l'applicazione FastAPI, gli endpoint, e la logica di integrazione con Pinecone e OpenAI
- `requirements.txt`: Elenco delle dipendenze Python
- `.env.example`: Template per le variabili d'ambiente

## 📝 Note Importanti

- Il sistema recupera i **top 3 documenti** più rilevanti da Pinecone
- Le risposte sono generate **esclusivamente** basandosi sui documenti recuperati da Pinecone
- Se non vengono trovati documenti rilevanti, viene restituito un errore 404
- I dati biometrici sono opzionali ma possono aiutare a personalizzare la risposta

## 🐛 Troubleshooting

### Errore: "OPENAI_API_KEY non trovata"

Assicurati di aver creato il file `.env` e configurato correttamente le variabili d'ambiente.

### Errore: "Nessun documento rilevante trovato in Pinecone"

Verifica che:
- L'indice Pinecone esista e sia configurato correttamente
- L'indice contenga documenti con metadata `text` o `content`
- Le dimensioni dei vettori siano corrette (default: 1536 per `text-embedding-ada-002`)

### Errore sulla porta su Render

Render assegna automaticamente una porta. Usa sempre `$PORT` nel comando di avvio.

## 📄 Licenza

Questo progetto è parte del sistema wellneAi.
