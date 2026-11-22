"""Public API request and response models."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    logo_url: str | None = None
    website: str | None = None


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: str
    title: str
    description: str | None = None
    country: str | None = None
    state: str | None = None
    city: str | None = None
    location: str | None = None
    job_latitude: float | None = None
    job_longitude: float | None = None
    posted_at_utc: datetime | None = None
    is_remote: bool | None = None
    employment_type: list[str] | None = None
    job_min_salary: int | None = None
    job_max_salary: int | None = None
    job_salary_period: str | None = None
    publisher: str | None = None
    apply_link: str | None = None
    apply_options: Any = None
    job_google_link: str | None = None
    job_highlights: Any = None
    job_benefits: str | None = None
    is_summarized: bool = False
    is_embedded: bool = False
    job_summary: str | None = None
    company: CompanyRead | None = None


class ProfileCreate(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,50}$")


class LocationUpdate(BaseModel):
    my_location: str = Field(min_length=1, max_length=200)


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    is_active: bool = False
    my_location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    filter_data: dict[str, Any]
    favorite_job_ids: list[str] = Field(default_factory=list)
    resume_filename: str | None = None
    resume_summary: str | None = None


class SearchRequest(BaseModel):
    keywords: str = Field(min_length=1, max_length=300)
    location: str | None = Field(default=None, max_length=200)
    country: str = Field(default="US", min_length=2, max_length=2)
    language: str = Field(default="en", min_length=2, max_length=5)
    date_posted: Literal["all", "today", "3days", "week", "month"] = "all"
    work_from_home: bool = False
    employment_types: list[str] = Field(default_factory=list)
    job_requirements: list[str] = Field(default_factory=list)
    distance_radius_miles: int | None = Field(default=None, ge=1, le=500)
    max_jobs: int = Field(default=100, ge=1, le=500)


class SearchResult(BaseModel):
    search_id: str
    job_ids: list[str]
    jobs: list[JobRead]
    total: int


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    job_ids: list[str] = Field(min_length=1, max_length=100)


class ChatRead(BaseModel):
    answer: str


class OperationRead(BaseModel):
    id: str
    kind: str
    status: Literal["queued", "running", "succeeded", "failed"]
    progress: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class BookmarkRead(BaseModel):
    job_id: str
    is_bookmarked: bool = True


class ResumeRead(BaseModel):
    has_resume: bool
    filename: str | None = None
    summary: str | None = None


class EmbeddingRequest(BaseModel):
    job_ids: list[str] = Field(min_length=1, max_length=500)


class AlertCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    filters: SearchRequest
    frequency: Literal["daily", "weekly"] = "daily"
    is_enabled: bool = True


class AlertUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    filters: SearchRequest | None = None
    frequency: Literal["daily", "weekly"] | None = None
    is_enabled: bool | None = None


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_name: str
    name: str
    filters: dict[str, Any]
    frequency: str
    is_enabled: bool
    created_at: datetime
    last_run_at: datetime | None = None
    next_run_at: datetime
    baseline_complete: bool
    last_error: str | None = None
    last_match_job_ids: list[str] = Field(default_factory=list)


class AlertRunRead(BaseModel):
    alert_id: int
    matched_job_ids: list[str]
    new_job_ids: list[str]
    jobs: list[JobRead]


class NotificationRead(BaseModel):
    id: int
    alert_id: int
    alert_name: str
    job_id: str
    title: str
    company_name: str | None = None
    location: str | None = None
    apply_link: str | None = None
    created_at: datetime
    read_at: datetime | None = None
