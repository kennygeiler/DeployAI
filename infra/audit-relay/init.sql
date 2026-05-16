-- Initialized on first Postgres startup (docker-entrypoint-initdb.d).
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    commit_sha VARCHAR(255),
    actor VARCHAR(255),
    changed_files TEXT,
    diff_summary TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
