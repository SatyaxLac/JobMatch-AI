from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session as OrmSession, joinedload

from api.dependencies import get_db, require_profile
from api.operations import create_operation
from api.schemas import AlertCreate, AlertRead, AlertUpdate, JobRead, NotificationRead, OperationRead
from api.tasks import run_alert_operation
from models_sql import Job, JobAlert, JobAlertNotification, Profile
from services.alert_service import create_alert, delete_alert, list_alerts, update_alert

router = APIRouter(prefix="/profiles", tags=["alerts"])


def _get_alert(db: OrmSession, profile_name: str, alert_id: int) -> JobAlert:
    alert = (
        db.query(JobAlert)
        .filter(JobAlert.id == alert_id, JobAlert.profile_name == profile_name)
        .first()
    )
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.get("/{profile_name}/alerts", response_model=list[AlertRead])
def get_alerts(
    profile_name: str,
    _profile: Profile = Depends(require_profile),
    db: OrmSession = Depends(get_db),
):
    return list_alerts(db, profile_name)


@router.post(
    "/{profile_name}/alerts",
    response_model=AlertRead,
    status_code=status.HTTP_201_CREATED,
)
def post_alert(
    profile_name: str,
    payload: AlertCreate,
    _profile: Profile = Depends(require_profile),
    db: OrmSession = Depends(get_db),
):
    return create_alert(
        db,
        profile_name,
        payload.name,
        payload.filters.model_dump(mode="json"),
        payload.frequency,
        payload.is_enabled,
    )


@router.patch("/{profile_name}/alerts/{alert_id}", response_model=AlertRead)
def patch_alert(
    profile_name: str,
    alert_id: int,
    payload: AlertUpdate,
    _profile: Profile = Depends(require_profile),
    db: OrmSession = Depends(get_db),
):
    alert = _get_alert(db, profile_name, alert_id)
    changes = payload.model_dump(exclude_unset=True, mode="json")
    return update_alert(db, alert, changes)


@router.delete("/{profile_name}/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_alert(
    profile_name: str,
    alert_id: int,
    _profile: Profile = Depends(require_profile),
    db: OrmSession = Depends(get_db),
):
    alert = _get_alert(db, profile_name, alert_id)
    delete_alert(db, alert)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{profile_name}/alerts/{alert_id}/run",
    response_model=OperationRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def run_saved_alert(
    profile_name: str,
    alert_id: int,
    background_tasks: BackgroundTasks,
    _profile: Profile = Depends(require_profile),
    db: OrmSession = Depends(get_db),
):
    alert = _get_alert(db, profile_name, alert_id)
    if not alert.is_enabled:
        raise HTTPException(status_code=409, detail="Alert is disabled")
    operation = create_operation("alert_run")
    background_tasks.add_task(
        run_alert_operation,
        operation["id"],
        profile_name,
        alert_id,
    )
    return operation


@router.get(
    "/{profile_name}/alerts/{alert_id}/matches",
    response_model=list[JobRead],
)
def get_alert_matches(
    profile_name: str,
    alert_id: int,
    _profile: Profile = Depends(require_profile),
    db: OrmSession = Depends(get_db),
):
    alert = _get_alert(db, profile_name, alert_id)
    job_ids = alert.last_match_job_ids or []
    if not job_ids:
        return []
    jobs = (
        db.query(Job)
        .options(joinedload(Job.company))
        .filter(Job.job_id.in_(job_ids))
        .all()
    )
    jobs_by_id = {job.job_id: job for job in jobs}
    return [jobs_by_id[job_id] for job_id in job_ids if job_id in jobs_by_id]


@router.get("/{profile_name}/notifications", response_model=list[NotificationRead])
def get_notifications(
    profile_name: str,
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    _profile: Profile = Depends(require_profile),
    db: OrmSession = Depends(get_db),
):
    query = (db.query(JobAlertNotification)
             .filter(JobAlertNotification.profile_name == profile_name)
             .order_by(JobAlertNotification.created_at.desc()))
    if unread_only:
        query = query.filter(JobAlertNotification.read_at.is_(None))
    notifications = query.limit(limit).all()
    job_ids = [notification.job_id for notification in notifications]
    jobs = (db.query(Job).options(joinedload(Job.company))
            .filter(Job.job_id.in_(job_ids)).all()) if job_ids else []
    jobs_by_id = {job.job_id: job for job in jobs}
    return [
        NotificationRead(
            id=notification.id,
            alert_id=notification.alert_id,
            alert_name=notification.alert.name,
            job_id=notification.job_id,
            title=jobs_by_id[notification.job_id].title if notification.job_id in jobs_by_id else "Job listing",
            company_name=(jobs_by_id[notification.job_id].company.name
                          if notification.job_id in jobs_by_id and jobs_by_id[notification.job_id].company
                          else None),
            location=jobs_by_id[notification.job_id].location if notification.job_id in jobs_by_id else None,
            apply_link=jobs_by_id[notification.job_id].apply_link if notification.job_id in jobs_by_id else None,
            created_at=notification.created_at,
            read_at=notification.read_at,
        )
        for notification in notifications
    ]


@router.patch("/{profile_name}/notifications/{notification_id}/read", response_model=NotificationRead)
def mark_notification_read(
    profile_name: str,
    notification_id: int,
    _profile: Profile = Depends(require_profile),
    db: OrmSession = Depends(get_db),
):
    notification = (db.query(JobAlertNotification)
                    .filter(JobAlertNotification.id == notification_id,
                            JobAlertNotification.profile_name == profile_name).first())
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.read_at = notification.read_at or datetime.now(timezone.utc)
    db.commit()
    db.refresh(notification)
    job = (db.query(Job).options(joinedload(Job.company))
           .filter(Job.job_id == notification.job_id).first())
    return NotificationRead(
        id=notification.id,
        alert_id=notification.alert_id,
        alert_name=notification.alert.name,
        job_id=notification.job_id,
        title=job.title if job else "Job listing",
        company_name=job.company.name if job and job.company else None,
        location=job.location if job else None,
        apply_link=job.apply_link if job else None,
        created_at=notification.created_at,
        read_at=notification.read_at,
    )
