# Job-Match

Job-Match is my job discovery workspace for finding, comparing, and evaluating opportunities. I built it around saved search profiles, a separate web frontend and API, and an AI assistant that can answer questions about job listings with optional resume context.

## What it does

- Searches job listings through JSearch using keywords, location, posting date, and remote-work filters.
- Saves profiles and bookmarked jobs in PostgreSQL.
- Shows search results in a list or on an interactive Leaflet map with custom markers.
- Provides a selected-job detail view with role information, salary when available, and application links.
- Uploads and summarizes resumes, then uses the summary as context for AI job discussions.
- Chunks and embeds job summaries locally with BGE-M3, storing vectors in PostgreSQL with pgvector.
- Answers questions about visible jobs through a pgvector retriever and a direct OpenAI chat call.
- Runs daily or weekly saved-search alerts in a background worker and surfaces new matches in the frontend.

## Stack

| Area | Technology |
| --- | --- |
| Frontend | React, TypeScript, Vite, Tailwind CSS, shadcn/ui patterns |
| Maps | Leaflet with OpenStreetMap tiles |
| API | FastAPI |
| Database | PostgreSQL 17, SQLAlchemy, pgvector |
| Cache and operation status | Redis |
| Job listings | JSearch via RapidAPI |
| AI | LangChain, local BGE-M3 embeddings, OpenAI chat and summarization |
| Deployment | Docker Compose |

## Run with Docker Compose

Copy `.env.example` to `.env` in the project root and add your JSearch RapidAPI key and OpenAI key. Optional integrations can stay blank.

```powershell
Copy-Item .env.example .env
```

Build and start the services:

```powershell
docker compose build
docker compose up -d
docker compose ps
```

Open the web application at `http://localhost:5173/` and the FastAPI docs at `http://localhost:8000/docs`.

Compose starts five services: `postgres-with-pgvector`, `redis`, `backend`, `worker`, and `frontend`. The API waits for PostgreSQL and Redis health checks; the frontend waits for the API health endpoint. The database and Redis are reachable from the backend and worker on the Compose network.

Check API initialization and worker startup:

```powershell
docker compose logs --tail=100 backend worker
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/api/v1/profiles
```

The health endpoint should return `{"status":"ok"}`. The profiles endpoint should include the default profile created during API startup. Then open the frontend and search using the configured JSearch key.

Run the service-layer unit tests in the backend image:

```powershell
docker compose exec backend python -m unittest discover -s tests -v
```

For local frontend development:

```sh
cd frontend
npm install
npm run dev
```

The API uses `VITE_API_BASE_URL` for its base URL; it defaults to `http://localhost:8000/api/v1`. If you are upgrading from the old Compose service names, run `docker compose down` before starting this split; this preserves the named `pgdata` volume unless you explicitly pass `-v`.

## Database migrations

A new PostgreSQL volume enables pgvector through `docker/postgres-init/001_enable_pgvector.sql`; the API creates tables at startup. For an existing database, apply migrations in order before deploying schema changes:

1. `migrations/001_job_embeddings_pgvector.sql` converts the existing embedding array to `vector(1024)` and adds a cosine index.
2. `migrations/002_job_alert_delivery.sql` adds scheduled alert state, seen-job records, run history, and in-app notifications.

## AI and alerts

Job summaries are chunked and embedded locally with `BAAI/bge-m3`. PostgreSQL `job_embeddings` stores the chunks and vectors. The AI chat retrieves relevant chunks for the visible search result IDs and sends that context, plus the profile's resume summary when present, to the configured OpenAI chat model. Select **Prepare jobs for AI** in the frontend before starting a chat with a newly searched result set.

The alert worker polls enabled alerts and checks their saved filters daily or weekly in UTC. It silently records the first run as a baseline and creates an in-app notification for each newly seen job on later runs. Notifications are scoped to the selected profile. Set `ALERT_WORKER_POLL_SECONDS` to change its polling interval.

## Configuration

| Variable | Purpose |
| --- | --- |
| `RAPID_API_KEY` | JSearch job search |
| `OPENAI_API_KEY` | Resume/job summaries and AI chat |
| `FINNHUB_API_KEY` | Optional company enrichment |
| `ABSTRACT_ENRICH_API_KEY` | Optional company enrichment |
| `COMPANY_ENRICH_API_KEY` | Optional company enrichment |
| `CORS_ORIGINS` | Comma-separated frontend origins allowed by FastAPI |
| `ALERT_WORKER_POLL_SECONDS` | Alert worker polling interval; defaults to 30 seconds |

Do not commit `.env` files or API credentials.

## Attribution and license

Job-Match is my modified derivative of [Job-Genius by Mani Amoozadeh](https://github.com/ManiAm/Job-Genius). The original project is distributed under the MIT License. I retain the original copyright and permission notice in [LICENSE](./LICENSE), as required by that license. I have renamed and extended the project, including its FastAPI backend, React frontend, pgvector AI workflow, and scheduled alert worker. This derivative is maintained independently and is not an official release of the original project.

The original MIT license is included in [LICENSE](./LICENSE).
