from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as OrmSession

from api.dependencies import get_db
from api.schemas import LocationUpdate, ProfileCreate, ProfileRead
from models_sql import Profile
from nominatim_api import get_coordinates

router = APIRouter(prefix="/profiles", tags=["profiles"])

DEFAULT_FILTERS = {
    "keywords": "software engineer",
    "location": "California",
    "country": "US",
    "language": "en",
    "date_posted": "all",
    "work_from_home": False,
    "employment_types": [],
    "job_requirements": [],
    "distance_radius": 50,
    "max_jobs": 100,
}


@router.get("", response_model=list[ProfileRead])
def get_profiles(db: OrmSession = Depends(get_db)):
    return db.query(Profile).order_by(Profile.name).all()


@router.post("", response_model=ProfileRead, status_code=status.HTTP_201_CREATED)
def create_profile(payload: ProfileCreate, db: OrmSession = Depends(get_db)):
    if db.query(Profile).filter(Profile.name == payload.name).first():
        raise HTTPException(status_code=409, detail="Profile already exists")
    profile = Profile(name=payload.name, filter_data=DEFAULT_FILTERS.copy())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/{profile_name}", response_model=ProfileRead)
def get_profile(profile_name: str, db: OrmSession = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.name == profile_name).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.put("/{profile_name}/filters", response_model=ProfileRead)
def save_profile_filters(
    profile_name: str,
    filters: dict,
    db: OrmSession = Depends(get_db),
):
    profile = db.query(Profile).filter(Profile.name == profile_name).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile.filter_data = filters
    db.commit()
    db.refresh(profile)
    return profile


@router.put("/{profile_name}/location", response_model=ProfileRead)
def update_profile_location(
    profile_name: str,
    payload: LocationUpdate,
    db: OrmSession = Depends(get_db),
):
    profile = db.query(Profile).filter(Profile.name == profile_name).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    success, result = get_coordinates(payload.my_location)
    if not success:
        raise HTTPException(status_code=422, detail=str(result))
    profile.my_location = payload.my_location
    profile.latitude, profile.longitude = result
    db.commit()
    db.refresh(profile)
    return profile
