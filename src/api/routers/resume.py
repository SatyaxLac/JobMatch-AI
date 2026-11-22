from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session as OrmSession

from api.dependencies import get_db, require_profile
from api.operations import create_operation
from api.schemas import OperationRead, ResumeRead
from api.tasks import run_resume_operation
from models_sql import Profile
from db_profiles import clear_resume

router = APIRouter(prefix="/profiles", tags=["resume"])
MAX_RESUME_BYTES = 15 * 1024 * 1024


@router.get("/{profile_name}/resume", response_model=ResumeRead)
def get_resume(profile: Profile = Depends(require_profile)):
    return ResumeRead(
        has_resume=bool(profile.resume_filename and profile.resume_binary),
        filename=profile.resume_filename,
        summary=profile.resume_summary,
    )


@router.put(
    "/{profile_name}/resume",
    response_model=OperationRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_resume(
    profile_name: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    profile: Profile = Depends(require_profile),
    db: OrmSession = Depends(get_db),
):
    contents = await file.read(MAX_RESUME_BYTES + 1)
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(contents) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=413, detail="Resume exceeds the 15 MB limit")

    profile.resume_filename = file.filename or "resume"
    profile.resume_binary = contents
    profile.resume_text = None
    profile.resume_summary = None
    db.commit()

    operation = create_operation("resume_processing")
    background_tasks.add_task(run_resume_operation, operation["id"], profile_name)
    return operation


@router.delete("/{profile_name}/resume", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume(
    profile_name: str,
    _profile: Profile = Depends(require_profile),
):
    clear_resume(profile_name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
