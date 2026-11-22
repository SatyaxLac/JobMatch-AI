"""Redis-backed status records for long-running API operations."""

import json
from datetime import datetime, timezone
from uuid import uuid4

from models_redis import redis_client

OPERATION_TTL_SECONDS = 24 * 60 * 60


def create_operation(kind: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    operation = {
        "id": str(uuid4()),
        "kind": kind,
        "status": "queued",
        "progress": "Queued",
        "result": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
    }
    _write(operation)
    return operation


def update_operation(operation_id: str, **changes) -> dict | None:
    operation = get_operation(operation_id)
    if operation is None:
        return None
    operation.update(changes)
    operation["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write(operation)
    return operation


def get_operation(operation_id: str) -> dict | None:
    value = redis_client.get(_key(operation_id))
    return json.loads(value) if value else None


def _write(operation: dict) -> None:
    redis_client.setex(
        _key(operation["id"]),
        OPERATION_TTL_SECONDS,
        json.dumps(operation),
    )


def _key(operation_id: str) -> str:
    return f"api:operation:{operation_id}"
