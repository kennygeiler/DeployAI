# Postgres 16 + pgvector (pre-bundled) + pgcrypto (contrib, activated via init SQL).
# Apache AGE 1.6.0 (PG16) layered on top for Cypher graph queries (v2 Phase 0a).
FROM pgvector/pgvector:pg16

ARG AGE_VERSION=1.6.0
ARG AGE_PG_LINE=PG16
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        flex \
        bison \
        postgresql-server-dev-16 \
    && curl -fsSL "https://dlcdn.apache.org/age/${AGE_PG_LINE}/${AGE_VERSION}/apache-age-${AGE_VERSION}-src.tar.gz" \
         -o /tmp/age.tar.gz \
    && mkdir -p /tmp/age-src \
    && tar -xzf /tmp/age.tar.gz -C /tmp/age-src --strip-components=1 \
    && make -C /tmp/age-src install \
    && rm -rf /tmp/age.tar.gz /tmp/age-src \
    && apt-get purge -y --auto-remove build-essential flex bison postgresql-server-dev-16 curl \
    && rm -rf /var/lib/apt/lists/*

COPY init/*.sql /docker-entrypoint-initdb.d/

# Fly mounts the persistent volume root-owned; the postgres base image
# can't chown it from non-root. This shim chowns $PGDATA as root before
# delegating to docker-entrypoint.sh. Harmless under docker-compose
# (volume there is already postgres-owned).
COPY fly-entrypoint.sh /usr/local/bin/fly-entrypoint.sh
RUN chmod +x /usr/local/bin/fly-entrypoint.sh
ENTRYPOINT ["fly-entrypoint.sh"]
CMD ["postgres"]
