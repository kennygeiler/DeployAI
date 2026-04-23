# Postgres 16 + pgvector (pre-bundled) + pgcrypto (contrib, activated via init SQL).
# Story 1.7 — docker-compose reference dev environment.
FROM pgvector/pgvector:pg16

COPY init/*.sql /docker-entrypoint-initdb.d/
