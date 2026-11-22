from fastapi import APIRouter, BackgroundTasks, Depends, status

from api.dependencies import require_profile
from api.operations import create_operation
from api.schemas import OperationRead, SearchRequest
from api.tasks import run_search_operation
from models_sql import Profile

router = APIRouter(prefix="/profiles", tags=["search"])


@router.post(
    "/{profile_name}/searches",
    response_model=OperationRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def search_jobs(
    profile_name: str,
    payload: SearchRequest,
    background_tasks: BackgroundTasks,
    _profile: Profile = Depends(require_profile),
):
    operation = create_operation("job_search")
    background_tasks.add_task(
        run_search_operation,
        operation["id"],
        profile_name,
        payload.model_dump(mode="json"),
    )
    return operation
