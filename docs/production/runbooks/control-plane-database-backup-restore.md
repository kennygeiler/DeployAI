# Runbook — CP Postgres backup & restore

Pilot defaults **PS-Q-101 / PS-O-104** — engineering restore owner until formal ops.

Human-operated: backup vendor consoles, privileged restores, connection secret rotation.

Skeleton: restore clone → verify `healthz` → migrate compatibility → update vault DSN → Gates 1–2.
