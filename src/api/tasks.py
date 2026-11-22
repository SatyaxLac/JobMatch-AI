"""Background task entry points for potentially long API operations."""

from sqlalchemy.orm import joinedload

from api.operations import update_operation
from api.schemas import JobRead, SearchRequest
from models_sql import Job, JobEmbedding, Profile, Session
from services.alert_service import run_alert
from services.enrichment_service import summarize_and_embed
from services.resume_service import summarize_resume
from services.search_service import start_job_search


def run_search_operation(operation_id: str, profile_name: str, request_data: dict) -> None:
    update_operation(operation_id, status="running", progress="Starting job search")
    try:
        request = SearchRequest.model_validate(request_data)
        with Session() as db_session:
            profile = db_session.query(Profile).filter(Profile.name == profile_name).first()
            if profile is None:
                raise ValueError("Profile not found")
            latitude, longitude = profile.latitude, profile.longitude

        job_ids = start_job_search(
            keywords=request.keywords,
            location=request.location or "",
            country=request.country,
            language=request.language,
            date_posted=request.date_posted,
            work_from_home=request.work_from_home,
            employment_types=",".join(request.employment_types) or None,
            job_requirements=",".join(request.job_requirements) or None,
            distance_radius=request.distance_radius_miles,
            my_latitude=latitude,
            my_longitude=longitude,
            max_jobs=request.max_jobs,
            on_progress=lambda message: update_operation(
                operation_id, status="running", progress=message
            ),
        )
        jobs = _serialize_jobs(job_ids)
        result = {
            "search_id": operation_id,
            "job_ids": job_ids,
            "jobs": jobs,
            "total": len(jobs),
        }
        update_operation(
            operation_id,
            status="succeeded",
            progress="Search complete",
            result=result,
        )
    except Exception as exc:
        update_operation(operation_id, status="failed", error=str(exc))


def run_embedding_operation(operation_id: str, job_ids: list[str]) -> None:
    update_operation(operation_id, status="running", progress="Preparing job embeddings")
    try:
        success, error = summarize_and_embed(
            job_ids,
            on_progress=lambda message: update_operation(
                operation_id, status="running", progress=message
            ),
        )
        if not success:
            raise RuntimeError(error or "Job embedding failed")

        with Session() as db_session:
            embedded_count = (
                db_session.query(Job)
                .filter(Job.job_id.in_(job_ids), Job.is_embedded.is_(True))
                .count()
            )
            chunk_count = (
                db_session.query(JobEmbedding)
                .join(Job, Job.id == JobEmbedding.job_id)
                .filter(Job.job_id.in_(job_ids))
                .count()
            )
        update_operation(
            operation_id,
            status="succeeded",
            progress="Embedding complete",
            result={"requested_jobs": len(job_ids), "embedded_jobs": embedded_count, "chunks": chunk_count},
        )
    except Exception as exc:
        update_operation(operation_id, status="failed", error=str(exc))


def run_resume_operation(operation_id: str, profile_name: str) -> None:
    update_operation(operation_id, status="running", progress="Preparing resume")
    try:
        success, error = summarize_resume(
            profile_name,
            on_progress=lambda message: update_operation(
                operation_id, status="running", progress=message
            ),
        )
        if not success:
            raise RuntimeError(error or "Resume processing failed")

        with Session() as db_session:
            profile = db_session.query(Profile).filter(Profile.name == profile_name).first()
            result = {
                "filename": profile.resume_filename if profile else None,
                "summary": profile.resume_summary if profile else None,
            }
        update_operation(
            operation_id,
            status="succeeded",
            progress="Resume ready",
            result=result,
        )
    except Exception as exc:
        update_operation(operation_id, status="failed", error=str(exc))


def run_alert_operation(operation_id: str, profile_name: str, alert_id: int) -> None:
    update_operation(operation_id, status="running", progress="Running saved search")
    try:
        success, result = run_alert(
            profile_name,
            alert_id,
            on_progress=lambda message: update_operation(
                operation_id, status="running", progress=message
            ),
        )
        if not success:
            raise RuntimeError(str(result))
        job_ids = result["matched_job_ids"]
        result["jobs"] = _serialize_jobs(job_ids)
        update_operation(
            operation_id,
            status="succeeded",
            progress="Alert run complete",
            result=result,
        )
    except Exception as exc:
        update_operation(operation_id, status="failed", error=str(exc))


def _serialize_jobs(job_ids: list[str]) -> list[dict]:
    if not job_ids:
        return []
    with Session() as db_session:
        jobs = (
            db_session.query(Job)
            .options(joinedload(Job.company))
            .filter(Job.job_id.in_(job_ids))
            .all()
        )
        jobs_by_id = {job.job_id: job for job in jobs}
        return [
            JobRead.model_validate(jobs_by_id[job_id]).model_dump(mode="json")
            for job_id in job_ids
            if job_id in jobs_by_id
        ]
