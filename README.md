# Longevity Backend

FastAPI backend for [Longevity](https://github.com/daro-hub/longevity), an AI nutrition assistant. The system uses Pinecone as a vector database to retrieve relevant scientific documents and GPT-4 to generate nutrition answers grounded exclusively in what those sources say.

**Live API:** https://longevity-backend-07su.onrender.com
**Frontend repository:** https://github.com/daro-hub/longevity

## The idea

Everything a nutritionist knows, they ultimately learned from documents — scientific papers, guidelines, studies. That's exactly the kind of knowledge a RAG (retrieval-augmented generation) system can consult and answer from, instead of guessing.

## What it does

- `POST /ask` — ask a nutrition question, answered only from indexed sources
- Optional biometric data (age, weight, height, activity level) to personalize the answer
- Semantic search over Pinecone to find the most relevant documents
- GPT-4 answer generation, grounded strictly in the retrieved context — if nothing relevant is found, it says so instead of making something up

## Requirements

- Python 3.11+
- OpenAI account with an API key
- Pinecone account with a configured index

## Local setup

1. **Clone the repository:**

```bash
git clone https://github.com/daro-hub/longevity-backend.git
cd longevity-backend
```

2. **Create and activate a virtual environment:**

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

3. **Install dependencies:**

```bash
pip install -r requirements.txt
```

4. **Configure environment variables:**

Copy `.env.example` to `.env` and fill in your keys:

```env
OPENAI_API_KEY=your-openai-api-key
PINECONE_API_KEY=your-pinecone-api-key
PINECONE_ENVIRONMENT=us-east1-gcp
PINECONE_INDEX_NAME=nutri-ai-knowledge
```

5. **Run the dev server:**

```bash
uvicorn main:app --reload
```

The server runs at `http://localhost:8000`. Interactive docs: Swagger UI at `/docs`, ReDoc at `/redoc`.

## Using `/ask`

```bash
curl -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is the recommended daily protein intake for an adult?",
    "user_data": { "age": 30, "weight": 75, "height": 175 }
  }'
```

`user_data` is optional — you can send just the question:

```json
{ "question": "What are the benefits of omega-3?" }
```

Response:

```json
{ "answer": "According to the available scientific sources..." }
```

## Deploy (Render)

1. Create a new Web Service on Render
2. Set the environment variables above in the "Environment" tab
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:$PORT`

## Code structure

- `main.py` — FastAPI app, endpoints, Pinecone/OpenAI integration
- `requirements.txt` — Python dependencies
- `.env.example` — environment variable template

## Notes

- The system retrieves the **top 3** most relevant documents from Pinecone
- Answers are generated **exclusively** from the retrieved context
- If no relevant document is found, the API returns a 404 instead of improvising
- Biometric data is optional but helps personalize the answer

## Troubleshooting

**"OPENAI_API_KEY not found"** — make sure you created `.env` and set the variables correctly.

**"No relevant document found in Pinecone"** — check that the Pinecone index exists, contains documents with `text` or `content` metadata, and that the vector dimensions match your embedding model (1536 for `text-embedding-ada-002`).

**Port errors on Render** — Render assigns the port automatically; always use `$PORT` in the start command, never a hardcoded port.
