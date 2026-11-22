"""
Job search orchestration — query JSearch, filter by distance, persist to Postgres.

No Streamlit dependency.  Progress goes through the *on_progress* callback.
"""

import re
import time
from typing import Callable, Optional
from datetime import datetime, timezone

from cleanco import basename

from nominatim_api import distance_between_coords
from models_sql import Session, Job, Company
from JSearch_api import JSearch_REST_API_Client

_jSearch = JSearch_REST_API_Client(url="https://jsearch.p.rapidapi.com")

_noop: Callable[[str], None] = lambda msg: None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_job_search(
    keywords: str,
    location: str,
    country: str,
    language: str,
    date_posted: str = "all",
    work_from_home: bool = False,
    employment_types: Optional[str] = None,
    job_requirements: Optional[str] = None,
    distance_radius: Optional[int] = None,
    my_latitude: Optional[float] = None,
    my_longitude: Optional[float] = None,
    max_jobs: int = 100,
    on_progress: Callable[[str], None] = _noop,
) -> list[str]:
    """
    Search for jobs via JSearch, filter by distance, persist to Postgres.

    Returns a list of external *job_id* strings.
    """
    page_num = 1
    num_pages = 10
    unique_job_ids: set[str] = set()
    result_list: list[dict] = []
    try_count = 1
    try_count_max = 1

    while True:
        on_progress(f"Querying jobs: page {page_num} ({num_pages} pages per request)...")

        status, output = _jSearch.job_search(
            keywords=keywords,
            location=location,
            country=country,
            language=language,
            date_posted=date_posted,
            work_from_home=work_from_home,
            employment_types=employment_types,
            job_requirements=job_requirements,
            page_num=page_num,
            num_pages=num_pages,
            timeout=90,
        )

        if status:
            if not output:
                break

            for job in output:
                job_id = job.get("job_id")
                if job_id and job_id not in unique_job_ids:
                    unique_job_ids.add(job_id)
                    if _is_candidate(job, distance_radius, my_latitude, my_longitude):
                        result_list.append(job)

            on_progress(f"🔍 Jobs found so far: {len(result_list)}")

            if len(result_list) >= max_jobs:
                break

            page_num += num_pages
            time.sleep(3)
        else:
            on_progress(f"Search attempt {try_count}/{try_count_max} failed: {output}")
            if try_count >= try_count_max:
                on_progress("Maximum retry limit reached.")
                break
            try_count += 1
            time.sleep(3)

    _insert_jobs_db(result_list)
    return [job["job_id"] for job in result_list if "job_id" in job]


# Backwards-compatible name for callers that used the original service API.
search_jobs = start_job_search


def normalize_company_name(name: str) -> str:
    name = basename(name)
    name = name.lower()
    name = re.sub(r"[\W_]+", " ", name)
    name = re.sub(r"\s+", " ", name)
    name = name.strip()
    name = name.capitalize()
    return name


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_candidate(job_details, distance_radius, my_latitude, my_longitude) -> bool:
    job_latitude = job_details.get("job_latitude")
    job_longitude = job_details.get("job_longitude")

    if not job_latitude or not job_longitude:
        return True
    if not distance_radius:
        return True
    if not my_latitude or not my_longitude:
        return True

    my_loc = (my_latitude, my_longitude)
    job_loc = (job_latitude, job_longitude)
    distance = distance_between_coords(my_loc, job_loc, unit="miles")

    return distance is None or distance <= distance_radius


def _insert_jobs_db(result_list: list[dict]) -> None:
    db_session = Session()
    added_at = datetime.now(timezone.utc)

    for job_data in result_list:
        job_id = job_data.get("job_id")
        if not job_id:
            continue

        existing = db_session.query(Job).filter_by(job_id=job_id).first()
        if existing:
            continue

        company_name = job_data.get("employer_name", "Unknown Company")
        company_name = normalize_company_name(company_name)
        company = db_session.query(Company).filter_by(name=company_name).first()

        if not company:
            company = Company(
                name=company_name,
                logo_url=job_data.get("employer_logo"),
                website=job_data.get("employer_website"),
            )
            db_session.add(company)
            db_session.flush()

        job = Job(
            job_id=job_id,
            added_at=added_at,
            country=job_data.get("job_country"),
            state=job_data.get("job_state"),
            city=job_data.get("job_city"),
            location=job_data.get("job_location"),
            job_latitude=job_data.get("job_latitude"),
            job_longitude=job_data.get("job_longitude"),
            title=job_data.get("job_title"),
            description=job_data.get("job_description"),
            job_highlights=job_data.get("job_highlights"),
            job_benefits=job_data.get("job_benefits"),
            posted_at_utc=job_data.get("job_posted_at_datetime_utc"),
            posted_at_ts=job_data.get("job_posted_at_timestamp"),
            is_remote=job_data.get("job_is_remote"),
            employment_type=job_data.get("job_employment_types", []),
            job_min_salary=job_data.get("job_min_salary"),
            job_max_salary=job_data.get("job_max_salary"),
            job_salary_period=job_data.get("job_salary_period"),
            publisher=job_data.get("job_publisher"),
            is_direct_apply=job_data.get("job_is_direct_apply"),
            apply_link=job_data.get("job_apply_link"),
            apply_options=job_data.get("job_apply_options"),
            job_google_link=job_data.get("job_google_link"),
            company=company,
        )
        db_session.add(job)

    db_session.commit()
