"""Persistence and scheduled execution for saved job-search alerts."""

from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.exc import IntegrityError

from models_sql import (
    JobAlert,
    JobAlertNotification,
    JobAlertRun,
    JobAlertSeenJob,
    Profile,
    Session,
)
from services.search_service import start_job_search

Progress = Callable[[str], None]


def list_alerts(db_session, profile_name: str) -> list[JobAlert]:
    return (
        db_session.query(JobAlert)
        .filter(JobAlert.profile_name == profile_name)
        .order_by(JobAlert.created_at.desc())
        .all()
    )


def create_alert(db_session, profile_name: str, name: str, filters: dict,
                 frequency: str, is_enabled: bool) -> JobAlert:
    alert = JobAlert(
        profile_name=profile_name,
        name=name,
        filters=filters,
        frequency=frequency,
        is_enabled=is_enabled,
        next_run_at=datetime.now(timezone.utc),
    )
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)
    return alert


def update_alert(db_session, alert: JobAlert, changes: dict) -> JobAlert:
    schedule_changed = "frequency" in changes or "filters" in changes
    for field, value in changes.items():
        if value is not None:
            setattr(alert, field, value)
    if schedule_changed:
        alert.next_run_at = datetime.now(timezone.utc)
    db_session.commit()
    db_session.refresh(alert)
    return alert


def delete_alert(db_session, alert: JobAlert) -> None:
    db_session.delete(alert)
    db_session.commit()


def _next_run(frequency: str, now: datetime) -> datetime:
    return now + timedelta(days=7 if frequency == "weekly" else 1)


def run_alert(profile_name: str, alert_id: int,
              on_progress: Progress = lambda _message: None) -> tuple[bool, dict | str]:
    """Execute saved filters, persist the seen baseline, and create in-app notifications."""
    now = datetime.now(timezone.utc)
    with Session() as db:
        alert = (db.query(JobAlert)
                 .filter(JobAlert.id == alert_id, JobAlert.profile_name == profile_name)
                 .with_for_update().first())
        profile = db.query(Profile).filter(Profile.name == profile_name).first()
        if alert is None or profile is None:
            return False, "Alert or profile not found"
        if not alert.is_enabled:
            return False, "Alert is disabled"

        filters = dict(alert.filters or {})
        latitude, longitude = profile.latitude, profile.longitude
        run = JobAlertRun(alert_id=alert.id, status="running", started_at=now)
        db.add(run)
        # The partial unique index is the cross-process lock shared by API and worker.
        alert.next_run_at = _next_run(alert.frequency, now)
        alert.last_error = None
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return False, "Alert is already running"
        run_id = run.id

    try:
        on_progress(f"Running alert: {filters.get('keywords', 'saved search')}")
        employment_types = filters.get("employment_types") or []
        job_requirements = filters.get("job_requirements") or []
        job_ids = list(dict.fromkeys(start_job_search(
            keywords=filters.get("keywords", "software engineer"),
            location=filters.get("location") or "",
            country=filters.get("country", "US"),
            language=filters.get("language", "en"),
            date_posted=filters.get("date_posted", "all"),
            work_from_home=filters.get("work_from_home", False),
            employment_types=",".join(employment_types) if employment_types else None,
            job_requirements=",".join(job_requirements) if job_requirements else None,
            distance_radius=filters.get("distance_radius_miles"),
            my_latitude=latitude,
            my_longitude=longitude,
            max_jobs=filters.get("max_jobs", 100),
            on_progress=on_progress,
        )))

        completed_at = datetime.now(timezone.utc)
        with Session() as db:
            alert = db.query(JobAlert).filter(JobAlert.id == alert_id).with_for_update().first()
            run = db.query(JobAlertRun).filter(JobAlertRun.id == run_id).first()
            if alert is None or run is None:
                return False, "Alert was removed while its search was running"

            seen = {row[0] for row in db.query(JobAlertSeenJob.job_id)
                    .filter(JobAlertSeenJob.alert_id == alert_id).all()}
            baseline = not alert.baseline_complete
            new_ids = [] if baseline else [job_id for job_id in job_ids if job_id not in seen]
            additions = [JobAlertSeenJob(alert_id=alert_id, job_id=job_id)
                         for job_id in job_ids if job_id not in seen]
            db.add_all(additions)
            if new_ids:
                db.add_all(JobAlertNotification(
                    profile_name=profile_name, alert_id=alert_id, job_id=job_id
                ) for job_id in new_ids)

            alert.baseline_complete = True
            alert.last_match_job_ids = job_ids
            alert.last_run_at = completed_at
            alert.next_run_at = _next_run(alert.frequency, completed_at)
            alert.last_error = None
            run.status = "succeeded"
            run.completed_at = completed_at
            run.matched_count = len(job_ids)
            run.new_job_count = len(new_ids)
            db.commit()
        on_progress(f"Alert complete: {len(job_ids)} matches, {len(new_ids)} new")
        return True, {
            "matched_job_ids": job_ids,
            "new_job_ids": new_ids,
            "baseline_seeded": baseline,
        }
    except Exception as exc:
        failed_at = datetime.now(timezone.utc)
        with Session() as db:
            alert = db.query(JobAlert).filter(JobAlert.id == alert_id).first()
            run = db.query(JobAlertRun).filter(JobAlertRun.id == run_id).first()
            if alert is not None:
                alert.last_error = str(exc)[:4000]
                alert.next_run_at = failed_at + timedelta(minutes=5)
            if run is not None:
                run.status = "failed"
                run.completed_at = failed_at
                run.error = str(exc)[:4000]
            db.commit()
        return False, str(exc)


def run_due_alerts_once(on_progress: Progress = lambda _message: None,
                        limit: int = 20) -> int:
    """Run a bounded batch of due enabled alerts; safe across multiple workers."""
    now = datetime.now(timezone.utc)
    with Session() as db:
        # Recover a worker that died while holding a run's database-level claim.
        stale_before = now - timedelta(hours=3)
        stale_runs = (db.query(JobAlertRun)
                      .filter(JobAlertRun.status == "running",
                              JobAlertRun.started_at < stale_before).all())
        for stale_run in stale_runs:
            stale_run.status = "failed"
            stale_run.completed_at = now
            stale_run.error = "Worker run expired after 3 hours"
            alert = db.query(JobAlert).filter(JobAlert.id == stale_run.alert_id).first()
            if alert is not None:
                alert.last_error = stale_run.error
                alert.next_run_at = now
        db.commit()
        due = (db.query(JobAlert.profile_name, JobAlert.id)
               .filter(JobAlert.is_enabled.is_(True), JobAlert.next_run_at <= now)
               .order_by(JobAlert.next_run_at.asc())
               .limit(limit).all())
    completed = 0
    for profile_name, alert_id in due:
        success, result = run_alert(
            profile_name, alert_id,
            on_progress=lambda message: on_progress(f"Alert {alert_id}: {message}"),
        )
        if success:
            completed += 1
        elif result != "Alert is already running":
            on_progress(f"Alert {alert_id} failed: {result}")
    return completed
