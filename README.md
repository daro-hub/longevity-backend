# Longevity Backend

FastAPI backend for [Longevity](https://github.com/daro-hub/longevity), an AI nutrition assistant.

Two things live here, and it matters which one you're looking at:

1. **A deterministic nutrition engine** (`app/domain/`) — pure, 100%-covered
   Python that computes BMI, BMR (Mifflin-St Jeor), TDEE, a calorie target,
   and a macro split from a user profile. No LLM involved, no network call,
   nothing that can hallucinate a number. Every constant it uses has a
   citation, enforced by a test — see `GET /v1/references`.
2. **A constrained meal-plan pipeline** (`app/llm/`, `POST /v1/plan`) — the
   model's output schema (`app.llm.schemas.MealPlanDraft`) carries only
   `{food_key, grams}` per item, no calorie or macro field anywhere. Every
   total is computed server-side from `data/foods/foods.it.json` against
   the engine's targets; a plan outside tolerance is repaired first for
   free (`app.domain.plan_fitting`, pure scaling/nudging, no LLM) and only
   then, at most once, sent back to the model with the server-computed
   deltas. If it still doesn't land, the response falls back to
   `plan_status: "targets_only"` — never a 500, never a silently-wrong plan.
3. **A retrieval-honest Q&A endpoint** (`app/rag/`, `POST /v1/ask`) —
   Pinecone semantic search with an actual similarity threshold: below it,
   the LLM isn't called at all and a deterministic "not in my sources"
   message is returned instead. Chunks carry page-accurate citations
   (`app/rag/paging.py` resolves a chunk's character offsets back to the
   PDF page it came from) and content-addressed ids (re-ingesting
   unchanged text is a no-op instead of overwriting a positional slot).
   The legacy `POST /ask` (no threshold, no citations, `top_k=3` always
   trusted) still exists unmodified until the frontend switches over.

**Live API:** https://longevity-backend-07su.onrender.com (free tier — the
first request after ~15 minutes of inactivity can take up to 25-30s while
the instance wakes up)
**Frontend repository:** https://github.com/daro-hub/longevity

## Current state (honest, not aspirational)

- ✅ `POST /v1/targets` — deterministic engine, real citations, 100% test
  coverage on `app/domain`.
- ✅ `POST /v1/plan` — constrained meal-plan generation. The LLM never
  writes a number; the food database (`data/foods/foods.it.json`, ~70
  items, Atwater-checked at load) is curated, not scraped, and only
  ~70 items — the full-catalogue version is future work.
- ✅ `GET /v1/references` — every numeric constant the engine uses, with
  its source.
- ✅ `POST /v1/ask` — similarity threshold (below it, no LLM call, an
  instant deterministic refusal), page-accurate citations, content-
  addressed vector ids. **Not yet tuned against a real labeled eval
  set** (`scripts/tune_threshold.py` doesn't exist yet, and the corpus
  hasn't been ingested into Pinecone yet either — `RETRIEVAL_MIN_SCORE`
  in `app/domain/references.py` is a documented placeholder). The corpus
  itself is one document so far: CREA's 2018 Italian dietary guidelines
  (`data/manifest.yaml`).
- ⚠️ `POST /ask` — kept unmodified (`top_k=3`, no threshold, no
  citations) until the frontend moves to `/v1/ask`. Will be deleted then.
- ❌ No auth, no per-user persistence yet.

## Requirements

- Python 3.11+
- OpenAI account with an API key
- Pinecone account with a configured index (only needed for `/ask`;
  `/v1/targets` and `/v1/references` have zero external dependencies)

## Local setup

```bash
git clone https://github.com/daro-hub/longevity-backend.git
cd longevity-backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt   # includes requirements.txt + test/lint tools
cp .env.example .env         # fill in OPENAI_API_KEY / PINECONE_* if you need /ask
uvicorn main:app --reload
```

Server runs at `http://localhost:8000`. Swagger UI at `/docs`, ReDoc at
`/redoc`.

## Tests

```bash
pytest tests/domain --cov=app.domain --cov-fail-under=100   # the engine, 100% covered
pytest tests                                                 # everything (engine + API, mocked)
ruff check app tests scripts
```

No test hits a real OpenAI or Pinecone API — `tests/api/test_ask.py`,
`tests/api/test_ask_v1.py`, and `tests/llm/test_planner.py` all mock both.
There is no `RUN_LIVE_LLM` integration test yet.

## Using `/v1/ask`

```bash
curl -X POST "http://localhost:8000/v1/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "Quante porzioni di frutta e verdura al giorno?", "locale": "it"}'
```

Response: `{"answer": "...[1]...", "grounded": true, "citations": [{"n": 1, "doc_id": "crea-2018", "title": "...", "page": "42", "score": 0.51, "snippet": "...", "url": "..."}], "disclaimer": "..."}`.

The model may only cite by writing `[n]` — never a document name or page
number itself (those are attached server-side from the citation array;
any `[n]` outside range is stripped before the response goes out). If
nothing clears `RETRIEVAL_MIN_SCORE`, `grounded` is `false`, `citations`
is empty, and the LLM is never called — the answer is a static,
localized "not in my sources" message.

## Using `/v1/plan`

```bash
curl -X POST "http://localhost:8000/v1/plan" \
  -H "Content-Type: application/json" \
  -d '{
    "age_years": 30, "sex": "male", "height_cm": 175, "weight_kg": 75,
    "activity_level": "moderate", "goal": "lose_weight", "locale": "it",
    "excluded_tags": ["fish"]
  }'
```

`excluded_tags` filters the food catalogue *before* it ever reaches the
model — an excluded food is never offerable, not just discouraged by a
prompt instruction. Response includes `targets` (same shape as
`/v1/targets`), `plan` (the day/meal/item structure with real food names),
and `plan_status`: `"ok"` (matched on the first try), `"repaired"` (fixed
by scaling/nudging or one LLM repair round-trip), or `"targets_only"`
(the plan didn't converge — the computed targets are still returned, just
without a matching meal plan).

Costs at most 2 LLM calls per request (one generation, at most one
repair). Requires `OPENAI_API_KEY`; Pinecone is not used by this route.

## Using `/v1/targets`

```bash
curl -X POST "http://localhost:8000/v1/targets" \
  -H "Content-Type: application/json" \
  -d '{
    "age_years": 30, "sex": "male", "height_cm": 175, "weight_kg": 75,
    "activity_level": "moderate", "goal": "maintain", "locale": "it"
  }'
```

`activity_level` must be one of `sedentary|light|moderate|active|very_active`;
`goal` one of `lose_weight|maintain|gain_muscle` — these are enums, not free
text, because a formula needs an exact PAL multiplier, not "pretty active".

Response includes `bmi`, `calories` (with `tdee_kcal`, `bmr_kcal`, whether a
safety floor was applied), `macros` (protein/carb/fat/fiber grams, with
`kcal_from_macros` as the authoritative calorie figure — it's recomputed
from the *rounded* grams, so it's a target an integer-gram meal plan can
actually hit), `hydration_ml`, and a localized `disclaimer` that the API
attaches unconditionally — never something the model could omit.

Some profiles are refused outright (`refused: true`, no `targets`): minors,
implausible age/height/weight, severe underweight BMI, or a handful of
health conditions screened from free-text `health_notes` (pregnancy,
diabetes, dialysis, eating disorders, active cancer treatment, and a few
others). See `app/domain/guardrails.py` for the exact rules and
`app/domain/references.py` for the citation behind every number.

## Using `/ask`

```bash
curl -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is the recommended daily protein intake for an adult?",
    "user_data": { "age": 30, "weight": 75, "height": 175 }
  }'
```

`user_data` is optional. See the "Current state" section above for what
this endpoint does *not* yet guarantee.

## Ingesting the corpus

```bash
python scripts/index_docs.py --namespace v2
```

Every source file must be listed in `data/manifest.yaml` (filename ->
doc_id/title/publisher/year/lang/url) — ingestion refuses an unlisted
file, because a filename alone ("crea-linee-guida-2018.pdf, p. 42") is a
useless citation. Source PDFs themselves live in `data/corpus/` and are
gitignored (not committed — only the manifest is), so a fresh checkout
needs them added back before this script has anything to index.

`--namespace` is required with no default: pointing this at the wrong
namespace and passing `--delete-existing --yes-really` is destructive for
that namespace specifically, which is the point of not defaulting it.
Re-running on unchanged text is a no-op (content-addressed ids), and a
partially-failed run exits non-zero instead of printing a false "success".

## Deploy (Render)

Configuration lives in `render.yaml` (previously this existed only as prose
in this README, which meant the running config was unversioned). Secrets
(`OPENAI_API_KEY`, `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`) are set in the
Render dashboard's Environment tab, not in the file.

## Code structure

```
main.py                  1-line shim: `from app.main import app` — keeps
                          `uvicorn main:app` working regardless of internal
                          refactors.
app/
  main.py                FastAPI app factory, CORS, router registration.
  config.py               Settings (pydantic-settings), no import-time crash
                          on missing env vars.
  clients.py              Lazily-constructed OpenAI/Pinecone clients.
  logging_config.py       Structured logging setup.
  domain/                 The deterministic engine. Pure, no I/O. Start here:
                          engine.py::compute_targets() is the one public entrypoint.
                          Also: food_db.py, nutrition.py, plan_fitting.py,
                          plan_tolerance.py — the food database and the
                          "sum everything server-side" machinery the LLM
                          plan pipeline is built on.
  llm/
    schemas.py             MealPlanDraft etc. — no numeric nutrition field
                          anywhere, by design (see module docstring).
    validator.py            Hard-fails (unknown food, banned tag, grams out
                          of range) vs. tolerance checks.
    planner.py              generate -> validate -> fit_to_targets -> one
                          LLM repair -> targets_only. LLMPlanClient is a
                          narrow Protocol so tests use a trivial fake
                          instead of mocking the OpenAI SDK.
    openai_client.py        The real implementation, via Structured Outputs.
    prompts/                plan_it.md / plan_en.md
  rag/
    manifest.py             Loads + validates data/manifest.yaml; the
                          enforcement point for "no unlisted file".
    paging.py               PageMap — resolves a character offset back to
                          the PDF page it came from.
    chunking.py             Text splitting with offsets preserved.
    ids.py                  Content-addressed vector ids.
    ingest.py               Pure chunk assembly (manifest + pages ->
                          citable, content-addressed chunks). No network.
    retrieve.py             Query-side: embed, query Pinecone, keep only
                          matches above RETRIEVAL_MIN_SCORE.
    citations.py            Numbered context blocks <-> structured
                          citations array; strips out-of-range [n] markers.
  api/
    routes/               health, targets, plan, ask_v1, references, ask (legacy)
    schemas.py            pydantic request/response models
    mappers.py            domain dataclasses <-> API schemas
    deps.py               request-scoped deps (auth is a stub — see below)
data/
  foods/foods.it.json     ~70 hand-curated foods, per-100g macros, Atwater-
                          checked at load (scripts/generate_food_db.py
                          regenerates it from the reviewable macro list).
  manifest.yaml           Corpus documents this repo can cite. Tracked in
                          git; the PDFs themselves (data/corpus/) are not.
scripts/
  index_docs.py           Pinecone ingestion CLI — thin wrapper around
                          app/rag/ingest.py.
  generate_food_db.py      Regenerates data/foods/foods.it.json.
tests/
  domain/                 100% coverage, includes golden-vector snapshots
  llm/                    validator + planner, fully mocked (no network)
  rag/                    paging/manifest/ingest/retrieve/citations, all
                          pure logic, no network, no real PDF required
  api/                    FastAPI TestClient, OpenAI/Pinecone mocked
```

## Known gaps (tracked, not hidden)

- **No auth yet.** `/ask` is fully public; anyone who finds the URL spends
  your OpenAI/Pinecone quota. `app/api/deps.py::current_user_stub` is a
  placeholder for Supabase JWT verification, not a security boundary.
- **`/ask` retrieval has no relevance threshold.** It always returns the
  3 nearest vectors, relevant or not. (`/v1/ask` fixes this; `/ask` is
  kept unmodified until the frontend switches over, then deleted.)
- **`RETRIEVAL_MIN_SCORE` is an unvalidated placeholder.** No corpus has
  been ingested into Pinecone yet (blocked on `OPENAI_API_KEY` /
  `PINECONE_API_KEY` being filled in) and `scripts/tune_threshold.py`
  (empirical threshold tuning against a labeled query set) doesn't exist
  yet either. Don't trust the current threshold value as tuned.
- **The corpus is one document.** CREA's 2018 Italian dietary guidelines.
  Real variety needs more sources in `data/manifest.yaml`.
- **Cold start.** Render's free tier sleeps after ~15 minutes idle.
- **`/v1/plan`'s food catalogue is ~70 items.** Enough to prove the
  validate-and-repair mechanism works, not enough for real variety over a
  multi-day plan. `/v1/plan` also isn't rate-limited yet — same exposure
  as `/ask` (see the auth gap above), and each call costs up to 2 LLM
  requests instead of 1.
- **`/v1/plan` currently generates one day, not a multi-day plan.** The
  schema (`app.llm.schemas.MealPlanDraft`) already supports multiple
  `days`, but nothing in the prompt or the API asks for more than one yet.

## Troubleshooting

**"Service not configured" (503) from `/ask`** — `OPENAI_API_KEY` /
`PINECONE_API_KEY` / `PINECONE_INDEX_NAME` aren't set. Check `.env` locally
or the Render dashboard in production. `GET /` reports exactly which ones
are missing.

**"No relevant document found" (404) from `/ask`** — the Pinecone index is
empty, or its vector dimension doesn't match `OPENAI_EMBEDDING_DIMENSIONS`
(1024 here — the code deliberately truncates `text-embedding-3-small`,
which is natively 1536-dimensional, to match the existing index).
