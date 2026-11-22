# CLAUDE.md - Job-Match Developer Reference

This file describes the current Job-Match implementation and its service boundaries.

## Purpose and stack

Job-Match is a job discovery application with a React/Vite frontend and FastAPI backend. It searches JSearch, stores job and profile data in PostgreSQL, caches selected external API responses in Redis, enriches company data through Finnhub, and provides AI summaries, semantic job retrieval, and application-document generation.

| Layer | Technology |
|---|---|
| UI | React, TypeScript, Vite, Tailwind, shadcn/ui |
| Relational and vector storage | PostgreSQL 17 + pgvector, SQLAlchemy, psycopg2 |
| Cache and rate limiting | Redis 7.4 |
| Job source | JSearch (RapidAPI / OpenWeb Ninja) |
| Company data | Finnhub; optional AbstractAPI and CompanyEnrich clients |
| Local embeddings and chunking | LangChain Hugging Face integration, Sentence Transformers, BAAI/bge-m3 |
| Chat and text generation | LangChain OpenAI integration, direct OpenAI API calls |
| Resume parsing | pdfplumber, python-docx, pytesseract, python-magic, html2text |
| Containers | Docker Compose: pgvector PostgreSQL, Redis, FastAPI backend, alert worker, and React/Vite frontend |

## AI architecture

The AI workflow runs in the application process. There is no RAG-Search service, Qdrant store, LiteLLM proxy, RAG-Search URL, or health-gate request.

- `services/enrichment_service.py` summarizes jobs with `gpt-6-luna`, chunks summaries with `RecursiveCharacterTextSplitter` using the BGE-M3 tokenizer, creates local BGE-M3 embeddings, and persists chunks and vectors to `job_embeddings`.
- `job_embeddings.embedding` is PostgreSQL `vector(1024)`. The `job_embeddings` table is the single source of truth for job vectors and chunk text.
- `services/retrieval_service.py` implements `PgVectorJobRetriever`. It embeds a query with the same local BGE-M3 model, filters to the supplied visible job IDs, ranks by cosine distance, and returns up to 10 matching chunks with a 0.7 similarity threshold.
- `services/chat_service.py` passes retrieved context and the optional resume summary to `gpt-6.2-sol` through LangChain's `ChatOpenAI` integration.
- `services/resume_service.py` summarizes uploaded resumes directly with `gpt-6-luna`. `services/personalized_service.py` generates tailored resumes and cover letters directly with `gpt-6.2-sol`.
- `services/embedding_utils.py` and `services/ai_provider.py` cache model clients within the app process. Set `OPENAI_API_KEY` for direct model calls. BGE-M3 model files are downloaded and cached on first use.

`src/config.py` holds the model IDs, local embedding model, chunk sizing, and map settings. The vector dimension must stay aligned between `config.embedding_dimensions`, `JobEmbedding.embedding`, and the selected embedding model.

## Database and migration

PostgreSQL runs the pgvector-enabled image `pgvector/pgvector:0.8.7-pg17-bookworm`. A fresh data volume enables the extension through `docker/postgres-init/001_enable_pgvector.sql`. Existing databases must run `migrations/001_job_embeddings_pgvector.sql` once before deploying the `Vector(1024)` model mapping. That migration checks the current BGE-M3 vector dimension, converts the array column, and creates a cosine HNSW index.

Main tables:

- `jobs`: external job ID, listing fields, summary, summary/embedding status, and company foreign key.
- `companies`: normalized company name, logo, and website.
- `job_embeddings`: job foreign key, chunk index, chunk text, and `vector(1024)` embedding.
- `profiles`: saved filters, location, favorite job IDs, and resume data/summary.
- `job_alerts`: per-profile saved filters, cadence, enabled state, and latest matches.
- `job_alert_seen_jobs`: durable per-alert job-ID ledger used to prevent repeat alerts.
- `job_alert_notifications`: in-app new-match notifications and their read timestamps.
- `job_alert_runs`: scheduled/manual execution history and failure details.

Apply `migrations/002_job_alert_delivery.sql` to existing databases after the pgvector migration. Fresh databases create these objects through `Base.metadata.create_all()`.

SQLAlchemy models are in `src/models_sql.py`; profile CRUD is in `src/db_profiles.py`. `Base.metadata.create_all()` creates missing tables but does not replace the migration for existing column types.

## Project layout

```text
frontend/
  src/lib/api/types.ts         TypeScript DTOs matching FastAPI schemas
  src/lib/api/client.ts        Typed fetch client and operation polling
  src/components/ui/           shadcn-style copied components
  src/components/JobMap.tsx    Leaflet map with custom job markers
  src/App.tsx                  Search dashboard, job detail, resume, and AI chat
  components.json              shadcn/ui configuration
  vite.config.ts               React and Tailwind Vite plugins
src/
  main.py                       Retired Streamlit entry point (not in Compose)
  api/
    main.py                     FastAPI app, CORS, lifespan, router registration
    schemas.py                  Pydantic API contracts
    operations.py               Redis-backed long-operation status
    tasks.py                    Background search, resume, embedding, alert tasks
    routers/                    Profiles, search, bookmarks, resume, embeddings, alerts
  display_jobs.py               Job cards, maps, and company details (UI passed in)
  config.py                     AI model IDs and app configuration
  models_sql.py                 PostgreSQL models, including pgvector
  models_redis.py               Redis cache key builder and helpers
  db_profiles.py                Profile CRUD
  services/
    search_service.py           JSearch -> distance filtering -> PostgreSQL
    enrichment_service.py       Direct summarization, chunking, and pgvector writes
    embedding_utils.py          Cached local BGE-M3 embeddings
    retrieval_service.py        Job-scoped LangChain pgvector retriever
    ai_provider.py              Cached direct LangChain/OpenAI chat calls
    chat_service.py              RAG prompt construction and direct chat
    resume_service.py            Resume extraction and summarization
    personalized_service.py      Tailored resume and cover-letter generation
    alert_service.py             Saved-search alert persistence and execution
  alert_worker.py               Dedicated scheduled-alert polling process
  JSearch_api.py, finnhub_api.py, nominatim_api.py, ...
                                External non-AI API clients
```

## Service-layer rules

- Service functions take plain inputs and return plain values or `(success, error)` tuples.
- Service modules do not import Streamlit or access `st.session_state`.
- Long-running service work reports progress through `on_progress: Callable[[str], None]`.
- UI code passes a callback such as `lambda message: st.write(message)`.
- AI provider failures are returned to the caller; there are no remote health-gate checks.

## Main workflows

### FastAPI backend scaffold

Run the backend container on port 8000; OpenAPI docs are at `/docs`. Routes are prefixed with `/api/v1`. Profile names scope requests because the current data model has named profiles but no user authentication. Add authentication and ownership checks before exposing this API to multiple users.

The React/Vite frontend is served on port 5173 and uses `VITE_API_BASE_URL` (default `http://localhost:8000/api/v1`). Its clean SaaS dashboard has a searchable result list, a selected-job detail panel, a Leaflet/OpenStreetMap map with custom markers, and a resume-aware AI chat sidebar. Its TypeScript DTOs and `frontend/src/lib/api/client.ts` match the Pydantic contracts in `src/api/schemas.py`.

- `GET/POST /profiles`, `GET /profiles/{name}`, and `PUT /profiles/{name}/filters`
- `POST /profiles/{name}/searches` starts a search operation.
- `POST /profiles/{name}/chat` asks the RAG assistant about supplied visible job IDs and uses the profile's resume summary when available.
- `GET/PUT/DELETE /profiles/{name}/bookmarks[/{job_id}]` manages bookmarks.
- `GET/PUT/DELETE /profiles/{name}/resume` reads metadata, uploads, or clears a resume.
- `POST /profiles/{name}/embeddings` starts pgvector indexing for job IDs.
- `GET/POST /profiles/{name}/alerts`, `PATCH/DELETE /profiles/{name}/alerts/{id}`, and `POST .../{id}/run` manage and manually run alerts. `GET /profiles/{name}/notifications` lists in-app notifications; `PATCH .../notifications/{id}/read` marks one read.
- `job-match-alert-worker` polls due alerts every 30 seconds (configurable with `ALERT_WORKER_POLL_SECONDS`) and runs searches sequentially. Alert cadence is UTC daily or weekly. The first run seeds a silent baseline; later runs notify only for job IDs absent from that alert's seen ledger. Failed runs retry after five minutes, and stale running claims expire after three hours.
- `GET /operations/{id}` polls the progress/results for background search, resume, embedding, and alert operations.

Manual long operations run as FastAPI background tasks in this initial scaffold. Operation records and `on_progress` messages are kept in Redis for 24 hours. Scheduled alerts run in a dedicated Compose worker; a partial unique database index prevents a manual run and scheduled run from processing the same alert concurrently.

### Search and display

1. `main.py` reads filters and calls `services.search_service.start_job_search()`.
2. The search service queries JSearch, filters by distance when coordinates are available, inserts new companies/jobs, and returns external job IDs.
3. `display_jobs.py` queries PostgreSQL and renders cards, filters, maps, favorites, and Finnhub details.

### Summarize and embed

1. `summarize_and_embed(job_ids, on_progress)` queries unsummarized jobs and invokes `gpt-6-luna` directly.
2. The BGE-M3 tokenizer splits each summary into 4,000-token chunks with 200-token overlap.
3. LangChain's Hugging Face embedding integration creates 1,024-dimensional vectors locally.
4. Chunk text and vectors are committed to `job_embeddings`; `jobs.is_embedded` is updated. There is no collection creation or vector re-upload step.

### Ask the assistant

1. The chat service builds `PgVectorJobRetriever` for the visible job IDs.
2. The retriever embeds the question locally and runs a cosine-distance query over `job_embeddings`.
3. Up to 10 relevant chunks and optional resume context form the prompt.
4. `gpt-6.2-sol` answers through a direct LangChain OpenAI call; the answer returns to `main.py` for display.

### Resume and cover letter

Resume files are extracted by `services/resume_service.py` using the installed PDF, DOCX, HTML, and OCR tools. Resume summaries use `gpt-6-luna`; personalized resumes and cover letters use `gpt-6.2-sol`. All calls use the same direct AI provider helper.

## Redis caching

`models_redis.cache_key(func_name, **kwargs)` builds cache keys from explicit names and values. JSearch responses use a one-hour TTL, Nominatim results use 24 hours, and company enrichment responses use the default ten-minute TTL. Finnhub rate limiting uses Redis sorted sets. The sidebar's cache clear action flushes the configured Redis database.

## Environment variables

| Variable | Used by |
|---|---|
| `OPENAI_API_KEY` | Direct LangChain chat and summarization calls |
| `RAPID_API_KEY` | JSearch |
| `FINNHUB_API_KEY` | Finnhub |
| `ABSTRACT_ENRICH_API_KEY` | AbstractAPI company enrichment |
| `COMPANY_ENRICH_API_KEY` | CompanyEnrich |
| `API_TOKEN` | Optional bearer token for generic REST clients |

The OpenAI key is passed into the app container through `docker-compose.yml`. Do not commit API keys.
