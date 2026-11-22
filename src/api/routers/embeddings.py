from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session as OrmSession

from api.dependencies import get_db, require_profile
from api.operations import create_operation
from api.schemas import EmbeddingRequest, OperationRead
from api.tasks import run_embedding_operation
from models_sql import Job, Profile

router = APIRouter(prefix="/profiles", tags=["embeddings"])


@router.post(
    "/{profile_name}/embeddings",
    response_model=OperationRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_embeddings(
    profile_name: str,
    payload: EmbeddingRequest,
    background_tasks: BackgroundTasks,
    _profile: Profile = Depends(require_profile),
    db: OrmSession = Depends(get_db),
):
    found_ids = {
        row[0]
        for row in db.query(Job.job_id).filter(Job.job_id.in_(payload.job_ids)).all()
    }
    missing_ids = sorted(set(payload.job_ids) - found_ids)
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail={"message": "Some jobs were not found", "job_ids": missing_ids},
        )

    operation = create_operation("job_embedding")
    background_tasks.add_task(
        run_embedding_operation,
        operation["id"],
        payload.job_ids,
    )
    return operation
