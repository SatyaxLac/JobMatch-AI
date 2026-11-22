-- Apply after 001_job_embeddings_pgvector.sql.
-- Existing alerts seed their seen ledger from the prior last-match snapshot.
ALTER TABLE job_alerts
    ADD COLUMN IF NOT EXISTS next_run_at timestamptz,
    ADD COLUMN IF NOT EXISTS baseline_complete boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS last_error text;

UPDATE job_alerts
SET next_run_at = COALESCE(last_run_at, created_at, now())
WHERE next_run_at IS NULL;

ALTER TABLE job_alerts
    ALTER COLUMN next_run_at SET DEFAULT now(),
    ALTER COLUMN next_run_at SET NOT NULL;

CREATE TABLE IF NOT EXISTS job_alert_seen_jobs (
    alert_id integer NOT NULL REFERENCES job_alerts(id) ON DELETE CASCADE,
    job_id varchar NOT NULL,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (alert_id, job_id)
);

CREATE TABLE IF NOT EXISTS job_alert_notifications (
    id serial PRIMARY KEY,
    profile_name varchar NOT NULL REFERENCES profiles(name) ON DELETE CASCADE,
    alert_id integer NOT NULL REFERENCES job_alerts(id) ON DELETE CASCADE,
    job_id varchar NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    read_at timestamptz,
    CONSTRAINT uq_job_alert_notification_job UNIQUE (alert_id, job_id)
);
CREATE INDEX IF NOT EXISTS ix_job_alert_notifications_profile_name
    ON job_alert_notifications(profile_name);
CREATE INDEX IF NOT EXISTS ix_job_alert_notifications_alert_id
    ON job_alert_notifications(alert_id);
CREATE INDEX IF NOT EXISTS ix_job_alert_notifications_created_at
    ON job_alert_notifications(created_at);
CREATE INDEX IF NOT EXISTS ix_job_alert_notifications_unread
    ON job_alert_notifications(profile_name, created_at DESC)
    WHERE read_at IS NULL;

CREATE TABLE IF NOT EXISTS job_alert_runs (
    id serial PRIMARY KEY,
    alert_id integer NOT NULL REFERENCES job_alerts(id) ON DELETE CASCADE,
    status varchar NOT NULL DEFAULT 'running',
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    matched_count integer NOT NULL DEFAULT 0,
    new_job_count integer NOT NULL DEFAULT 0,
    error text
);
CREATE INDEX IF NOT EXISTS ix_job_alert_runs_alert_id ON job_alert_runs(alert_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_job_alert_runs_active_alert
    ON job_alert_runs(alert_id) WHERE status = 'running';

INSERT INTO job_alert_seen_jobs(alert_id, job_id)
SELECT alert.id, match.job_id
FROM job_alerts AS alert
CROSS JOIN LATERAL unnest(COALESCE(alert.last_match_job_ids, ARRAY[]::varchar[])) AS match(job_id)
ON CONFLICT (alert_id, job_id) DO NOTHING;

UPDATE job_alerts
SET baseline_complete = true
WHERE COALESCE(cardinality(last_match_job_ids), 0) > 0;
