from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session as OrmSession, joinedload

from api.dependencies import get_db, require_profile
from api.schemas import BookmarkRead, JobRead
from db_profiles import update_favorite_job
from models_sql import Job, Profile

router = APIRouter(prefix="/profiles", tags=["bookmarks"])


@router.get("/{profile_name}/bookmarks", response_model=list[JobRead])
def list_bookmarks(
    profile_name: str,
    profile: Profile = Depends(require_profile),
    db: OrmSession = Depends(get_db),
):
    bookmarked_ids = profile.favorite_job_ids or []
    if not bookmarked_ids:
        return []
    jobs = (
        db.query(Job)
        .options(joinedload(Job.company))
        .filter(Job.job_id.in_(bookmarked_ids))
        .all()
    )
    jobs_by_id = {job.job_id: job for job in jobs}
    return [jobs_by_id[job_id] for job_id in bookmarked_ids if job_id in jobs_by_id]


@router.put(
    "/{profile_name}/bookmarks/{job_id}",
    response_model=BookmarkRead,
)
def add_bookmark(
    profile_name: str,
    job_id: str,
    _profile: Profile = Depends(require_profile),
    db: OrmSession = Depends(get_db),
):
    if db.query(Job.id).filter(Job.job_id == job_id).first() is None:
        raise HTTPException(status_code=404, detail="Job not found")
    update_favorite_job(profile_name, job_id, add=True)
    return BookmarkRead(job_id=job_id, is_bookmarked=True)


@router.delete(
    "/{profile_name}/bookmarks/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_bookmark(
    profile_name: str,
    job_id: str,
    _profile: Profile = Depends(require_profile),
):
    update_favorite_job(profile_name, job_id, add=False)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
