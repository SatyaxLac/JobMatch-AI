"""Unit tests for the JSearch orchestration service."""

import unittest
from unittest.mock import patch

from services import search_service


class StartJobSearchTests(unittest.TestCase):
    @patch("services.search_service._insert_jobs_db")
    @patch("services.search_service.time.sleep")
    @patch("services.search_service.distance_between_coords")
    @patch("services.search_service._jSearch.job_search")
    def test_deduplicates_filters_and_reports_progress(
        self,
        job_search,
        distance_between_coords,
        sleep,
        insert_jobs,
    ):
        first_job = {
            "job_id": "job-1",
            "job_latitude": 37.3,
            "job_longitude": -121.9,
        }
        missing_coordinates = {"job_id": "job-2"}
        outside_radius = {
            "job_id": "job-3",
            "job_latitude": 40.7,
            "job_longitude": -74.0,
        }
        job_search.return_value = (
            True,
            [first_job, dict(first_job), missing_coordinates, outside_radius],
        )
        distance_between_coords.side_effect = [5.0, 3000.0]
        progress = []

        result = search_service.start_job_search(
            keywords="developer",
            location="San Jose",
            country="US",
            language="en",
            distance_radius=50,
            my_latitude=37.3,
            my_longitude=-121.9,
            max_jobs=2,
            on_progress=progress.append,
        )

        self.assertEqual(result, ["job-1", "job-2"])
        self.assertEqual(insert_jobs.call_args.args[0], [first_job, missing_coordinates])
        self.assertEqual(job_search.call_count, 1)
        self.assertEqual(distance_between_coords.call_count, 2)
        self.assertTrue(any("page 1" in message for message in progress))
        self.assertTrue(any("Jobs found so far: 2" in message for message in progress))
        sleep.assert_not_called()

    @patch("services.search_service._insert_jobs_db")
    @patch("services.search_service.time.sleep")
    @patch("services.search_service._jSearch.job_search", return_value=(False, "missing key"))
    def test_failed_provider_search_returns_empty_list_and_reports_failure(
        self,
        _job_search,
        sleep,
        insert_jobs,
    ):
        progress = []

        result = search_service.start_job_search(
            keywords="developer",
            location="",
            country="US",
            language="en",
            on_progress=progress.append,
        )

        self.assertEqual(result, [])
        insert_jobs.assert_called_once_with([])
        sleep.assert_not_called()
        self.assertTrue(any("missing key" in message for message in progress))
        self.assertTrue(any("Maximum retry limit reached" in message for message in progress))


if __name__ == "__main__":
    unittest.main()
