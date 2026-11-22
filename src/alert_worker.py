"""Dedicated polling worker for scheduled saved-search alerts."""

import logging
import os
import time

from services.alert_service import run_due_alerts_once

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("job_alert_worker")


def main() -> None:
    poll_seconds = max(5, int(os.getenv("ALERT_WORKER_POLL_SECONDS", "30")))
    logger.info("Alert worker started; polling every %s seconds", poll_seconds)
    while True:
        try:
            completed = run_due_alerts_once(on_progress=logger.info)
            if completed:
                logger.info("Completed %s due alert(s)", completed)
        except Exception:
            logger.exception("Alert polling cycle failed")
        time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
