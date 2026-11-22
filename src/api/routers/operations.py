from fastapi import APIRouter, HTTPException

from api.operations import get_operation
from api.schemas import OperationRead

router = APIRouter(prefix="/operations", tags=["operations"])


@router.get("/{operation_id}", response_model=OperationRead)
def read_operation(operation_id: str):
    operation = get_operation(operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="Operation not found or expired")
    return operation
