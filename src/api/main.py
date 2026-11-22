"""FastAPI application exposing Job-Match services to web clients."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import alerts, bookmarks, chat, embeddings, operations, profiles, resume, search
from models_sql import Profile, Session, init_db

DEFAULT_FILTERS = {
    "keywords": "software engineer",
    "location": "California",
    "country": "US",
    "language": "en",
    "date_posted": "all",
    "work_from_home": False,
    "employment_types": [],
    "job_requirements": [],
    "distance_radius": 50,
    "max_jobs": 100,
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with Session() as db_session:
        if db_session.query(Profile).filter(Profile.name == "default").first() is None:
            db_session.add(
                Profile(name="default", is_active=True, filter_data=DEFAULT_FILTERS.copy())
            )
            db_session.commit()
    yield


app = FastAPI(
    title="Job-Match API",
    version="1.0.0",
    description="REST API for job search, profiles, bookmarks, resumes, embeddings, and alerts.",
    lifespan=lifespan,
)

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

api_prefix = "/api/v1"
app.include_router(profiles.router, prefix=api_prefix)
app.include_router(search.router, prefix=api_prefix)
app.include_router(bookmarks.router, prefix=api_prefix)
app.include_router(resume.router, prefix=api_prefix)
app.include_router(embeddings.router, prefix=api_prefix)
app.include_router(alerts.router, prefix=api_prefix)
app.include_router(chat.router, prefix=api_prefix)
app.include_router(operations.router, prefix=api_prefix)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}
