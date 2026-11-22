"""Shared FastAPI dependencies for PostgreSQL sessions and profile scope."""

from collections.abc import Generator

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session as OrmSession

from models_sql import Profile, Session


def get_db() -> Generator[OrmSession, None, None]:
    db = Session()
    try:
        yield db
    finally:
        db.close()


def require_profile(
    profile_name: str,
    db: OrmSession = Depends(get_db),
) -> Profile:
    profile = db.query(Profile).filter(Profile.name == profile_name).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile
