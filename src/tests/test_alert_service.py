"""Unit tests for saved-search alert scheduling and first-seen delivery."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from models_sql import JobAlert, JobAlertNotification, JobAlertRun, JobAlertSeenJob
from services import alert_service


class FakeQuery:
    def __init__(self, model, alert, profile, run, seen_ids):
        self.model = model
        self.alert = alert
        self.profile = profile
        self.run = run
        self.seen_ids = seen_ids

    def filter(self, *_conditions):
        return self

    def with_for_update(self):
        return self

    def first(self):
        if self.model is JobAlert:
            return self.alert
        if self.model.__name__ == "Profile":
            return self.profile
        if self.model is JobAlertRun:
            return self.run
        return None

    def all(self):
        if self.model is JobAlertSeenJob.job_id:
            return [(job_id,) for job_id in self.seen_ids]
        return []


class FakeSession:
    def __init__(self, alert, profile, run=None, seen_ids=()):
        self.alert = alert
        self.profile = profile
        self.run = run
        self.seen_ids = set(seen_ids)
        self.added = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def query(self, model, *_args, **_kwargs):
        return FakeQuery(model, self.alert, self.profile, self.run, self.seen_ids)

    def add(self, item):
        self.added.append(item)
        if isinstance(item, JobAlertRun):
            item.id = 41
            self.run = item

    def add_all(self, items):
        self.added.extend(items)

    def commit(self):
        return None

    def rollback(self):
        return None


def make_alert(baseline_complete=False):
    return JobAlert(
        id=9,
        profile_name="default",
        name="Backend roles",
        filters={"keywords": "backend engineer", "country": "US", "language": "en"},
        frequency="daily",
        is_enabled=True,
        baseline_complete=baseline_complete,
        last_match_job_ids=[],
    )


class AlertServiceTests(unittest.TestCase):
    def setUp(self):
        self.profile = type("ProfileStub", (), {"latitude": 37.3, "longitude": -121.9})()

    def test_next_run_uses_daily_and_weekly_cadence(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)

        self.assertEqual(alert_service._next_run("daily", now), now + timedelta(days=1))
        self.assertEqual(alert_service._next_run("weekly", now), now + timedelta(days=7))

    @patch("services.alert_service.start_job_search", return_value=["job-1", "job-2"])
    def test_first_run_seeds_baseline_without_notifying(self, _start_search):
        alert = make_alert(baseline_complete=False)
        run = JobAlertRun(alert_id=alert.id)
        first_session = FakeSession(alert, self.profile)
        second_session = FakeSession(alert, self.profile, run=run)
        progress = []

        with patch("services.alert_service.Session", side_effect=[first_session, second_session]):
            success, result = alert_service.run_alert("default", alert.id, progress.append)

        self.assertTrue(success)
        self.assertEqual(result["matched_job_ids"], ["job-1", "job-2"])
        self.assertEqual(result["new_job_ids"], [])
        self.assertTrue(result["baseline_seeded"])
        self.assertTrue(alert.baseline_complete)
        self.assertEqual(alert.last_match_job_ids, ["job-1", "job-2"])
        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.new_job_count, 0)
        self.assertFalse(any(isinstance(item, JobAlertNotification) for item in second_session.added))
        self.assertEqual(sum(isinstance(item, JobAlertSeenJob) for item in second_session.added), 2)
        self.assertTrue(any("Alert complete" in message for message in progress))

    @patch("services.alert_service.start_job_search", return_value=["job-old", "job-new"])
    def test_later_run_notifies_only_for_unseen_jobs(self, _start_search):
        alert = make_alert(baseline_complete=True)
        run = JobAlertRun(alert_id=alert.id)
        first_session = FakeSession(alert, self.profile)
        second_session = FakeSession(alert, self.profile, run=run, seen_ids={"job-old"})

        with patch("services.alert_service.Session", side_effect=[first_session, second_session]):
            success, result = alert_service.run_alert("default", alert.id)

        self.assertTrue(success)
        self.assertEqual(result["new_job_ids"], ["job-new"])
        self.assertFalse(result["baseline_seeded"])
        self.assertEqual(run.new_job_count, 1)
        notifications = [
            item for item in second_session.added
            if isinstance(item, JobAlertNotification)
        ]
        self.assertEqual([item.job_id for item in notifications], ["job-new"])
        added_seen = [
            item.job_id for item in second_session.added
            if isinstance(item, JobAlertSeenJob)
        ]
        self.assertEqual(added_seen, ["job-new"])


if __name__ == "__main__":
    unittest.main()
