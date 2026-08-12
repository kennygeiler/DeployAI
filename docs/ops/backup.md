# Backups — Postgres dump + tenant-DEK metadata

Two backup paths exist, one per deployment mode:

| Path | Target DB | Mechanism | Schedule |
|------|-----------|-----------|----------|
| **Compose** (`make backup`) | local docker-compose Postgres | `scripts/backup.sh` | manual / host cron |
| **Railway production** | `postgres` service in the Railway project `deployai` | Railway volume backups + documented manual `pg_dump` | volume backups scheduled in the dashboard; pg_dump manual |

The compose path is documented first (it predates the cloud deploy); the
Railway path is in the
"[Railway production backups](#railway-production-backups)" section
below. The Fly.io-era path (nightly `pg_dump` → S3 via
`scripts/fly-backup.sh` + `.github/workflows/fly-backup.yml`) was retired
in the 2026-08-11 Railway migration — the workflow is deleted and the
scripts are archived under [`scripts/archive/`](../../scripts/archive/README.md).
**Not covered by either path:** MinIO object-storage artifacts (uploaded
meeting audio, email bodies in `s3` mode) — that is ticket H3 follow-up
work; until then a restore recovers the database but not uploaded
artifact blobs.

## `make backup` (compose path)

Per ORCHESTRATOR.md §4 D3: `make backup` writes a `pg_dump` of the
control-plane Postgres plus a small JSON document of tenant-DEK key
metadata to an S3 bucket (or a MinIO bucket exposing the S3 API).

The DEK ciphertext itself is **never** read or transmitted by this
script — only `(tenant_id, name, dek_key_id)` tuples that point at the
KMS-side material the dump must be decrypted alongside.

## Environment variables

| Var                       | Required | Default               | Notes                                                          |
|---------------------------|----------|-----------------------|----------------------------------------------------------------|
| `S3_BUCKET`               | **yes**  | —                     | Script refuses to run unset (avoids masking prod misconfig).   |
| `S3_PREFIX`               | no       | `deployai/backups`    | Key prefix under the bucket.                                   |
| `S3_ENDPOINT_URL`         | no       | (empty → real AWS)    | Set to `http://localhost:9000` for the dev MinIO container.    |
| `AWS_REGION`              | no       | `us-east-1`           | Forwarded to `aws s3 cp --region`.                             |
| `AWS_ACCESS_KEY_ID`       | yes      | —                     | Standard AWS env. For MinIO use the `MINIO_ROOT_USER` value.   |
| `AWS_SECRET_ACCESS_KEY`   | yes      | —                     | Standard AWS env. For MinIO use the `MINIO_ROOT_PASSWORD`.     |
| `POSTGRES_USER`           | no       | `deployai`            | DB role passed to `pg_dump`.                                   |
| `POSTGRES_DB`             | no       | `deployai`            | DB name passed to `pg_dump`.                                   |
| `COMPOSE_FILE`            | no       | `infra/compose/docker-compose.yml` | Override only when running against a non-default stack. |
| `COMPOSE_ENV_FILE`        | no       | `infra/compose/.env`  | Used when present.                                             |

## Local dev (MinIO) quickstart

The reference compose stack already runs MinIO on
`http://localhost:9000` with credentials `MINIO_ROOT_USER` /
`MINIO_ROOT_PASSWORD` (defaults `deployai` / `deployai-local-dev`).

```bash
make dev                                 # stack must be up

# One-time: create the destination bucket via the MinIO client.
docker run --rm --network deployai_default \
  --entrypoint sh minio/mc -c "
    mc alias set local http://minio:9000 deployai deployai-local-dev &&
    mc mb --ignore-existing local/deployai-dev-backups
  "

export S3_BUCKET=deployai-dev-backups
export S3_ENDPOINT_URL=http://localhost:9000
export AWS_ACCESS_KEY_ID=deployai
export AWS_SECRET_ACCESS_KEY=deployai-local-dev
make backup
```

The script prints the destination URI and uploaded byte counts on
success. It never echoes dump contents to stdout.

## Production

Point `S3_BUCKET` at a real bucket and leave `S3_ENDPOINT_URL` unset so
the AWS CLI resolves the public S3 endpoint for `AWS_REGION`. Use IAM
role credentials on the host (omit the static `AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY`) where the host supports it.

## Outputs

Each invocation creates one timestamped folder under
`s3://${S3_BUCKET}/${S3_PREFIX}/`:

```
${S3_PREFIX}/20260524T172500Z/
  postgres.dump      # pg_dump --format=custom (compressed)
  dek_metadata.json  # {"tenants": [{"id", "name", "dek_key_id"}, ...]}
```

## Restore outline

A full restore is **not** automated; it requires a deliberate sequence
that an operator should run by hand:

1. **Provision** a Postgres instance at the target version (currently 16
   + `pgcrypto` + `pgvector`).
2. **Restore the dump:**
   ```bash
   pg_restore --no-owner --no-privileges --dbname=deployai postgres.dump
   ```
   `--no-owner --no-privileges` matches the flags the dump was taken
   with so role names don't have to round-trip across deployments.
3. **Re-attach DEKs.** For each tenant in `dek_metadata.json`, ensure
   the KMS key referenced by `dek_key_id` exists in the destination
   account and that the wrapped `tenant_dek_ciphertext` column in
   `app_tenants` can be unwrapped against it. (The wrapped ciphertext
   travels in the dump; only the key-id catalogue needs separate
   reconciliation.)
4. **Run Alembic** against the restored DB to bring the schema to the
   migration head the application was at when the dump was taken:
   ```bash
   alembic upgrade head
   ```
5. **Smoke** with `make dev-verify` against the restored stack before
   directing traffic at it.

## Security envelope

- Never prints the DEK secret value — the CLI selects only `id`, `name`,
  and `tenant_dek_key_id` from `app_tenants`.
- `pg_dump` output is written to a temp file inside `mktemp -d` and
  uploaded by reference; nothing in the dump touches stdout.
- The script refuses to start without `S3_BUCKET` so a missing prod env
  var fails loud instead of writing to `/tmp` or a default local path.
- No outbound telemetry. No third-party logging.

## Restore procedure

`make restore` is the automated companion to `make backup`. It pulls
the dump + DEK manifest from an S3 prefix and replays the dump into
the running control-plane Postgres. **This overwrites the live DB** —
the script is wrapped in two opt-in env-var gates that you must set
deliberately each time.

### Safety gates

| Var                                | Required when                                                  | Effect                                                                                  |
|------------------------------------|----------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| `DEPLOYAI_RESTORE_CONFIRM=YES`     | **always**                                                     | Acknowledges that the run will overwrite the target DB. Restore refuses without this.   |
| `DEPLOYAI_RESTORE_FORCE_OVERWRITE=YES` | target DB already has rows in `app_tenants`                | Second opt-in for the "I really mean it" case. Refuses to clobber populated state otherwise. |

The double gate is intentional: a naive operator who runs `make
restore` against the wrong stack hits a hard wall *twice* before any
data is destroyed.

### Required env vars

| Var                       | Required | Default               | Notes                                                          |
|---------------------------|----------|-----------------------|----------------------------------------------------------------|
| `BACKUP`                  | **yes**  | —                     | `s3://bucket/prefix/<TIMESTAMP>/` written by `make backup`.    |
| `AWS_ACCESS_KEY_ID`       | yes      | —                     | Standard AWS env. For MinIO use the `MINIO_ROOT_USER` value.   |
| `AWS_SECRET_ACCESS_KEY`   | yes      | —                     | Standard AWS env. For MinIO use the `MINIO_ROOT_PASSWORD`.     |
| `S3_ENDPOINT_URL`         | no       | (empty → real AWS)    | Set to `http://localhost:9000` for the dev MinIO container.    |
| `AWS_REGION`              | no       | `us-east-1`           | Forwarded to `aws s3 cp --region`.                             |
| `POSTGRES_USER`           | no       | `deployai`            | DB role passed to `pg_restore`.                                |
| `POSTGRES_DB`             | no       | `deployai`            | DB name passed to `pg_restore`.                                |

### Verify-then-confirm flow

1. **Pull the artifacts** from S3 into a temp dir. The script aborts
   if `postgres.dump` is zero bytes (an empty dump would silently
   truncate the target DB on restore).
2. **Print the DEK manifest to stderr** so the operator can eyeball
   the tenant set they're about to clobber and `Ctrl-C` if the wrong
   prefix was supplied. The destructive step has not happened yet.
3. **Probe the target DB** for existing rows in `app_tenants`. If any
   rows exist and `DEPLOYAI_RESTORE_FORCE_OVERWRITE=YES` is *not* set,
   the script exits 2 with a clear message and changes nothing.
4. **Replay the dump** via `pg_restore --single-transaction
   --clean --if-exists`. The `--single-transaction` flag is
   load-bearing: any failure mid-restore rolls the whole thing back
   so the target DB is never left in a half-restored state.

### Example

```bash
make dev                                 # stack must be up

export BACKUP=s3://deployai-dev-backups/deployai/backups/20260524T172500Z/
export S3_ENDPOINT_URL=http://localhost:9000
export AWS_ACCESS_KEY_ID=deployai
export AWS_SECRET_ACCESS_KEY=deployai-local-dev
export DEPLOYAI_RESTORE_CONFIRM=YES
# Only needed when the target DB already has data:
# export DEPLOYAI_RESTORE_FORCE_OVERWRITE=YES

make restore BACKUP="$BACKUP"
```

After restore, run `make dev-verify` to smoke the restored stack
before directing traffic at it.

### Restore security envelope

- Refuses to run without `DEPLOYAI_RESTORE_CONFIRM=YES`. This is the
  loudest possible guard because the operation overwrites live data.
- Refuses to clobber a non-empty target DB without a second opt-in
  via `DEPLOYAI_RESTORE_FORCE_OVERWRITE=YES`.
- Verifies the pulled dump file is non-empty before invoking the
  destructive step; an empty dump would otherwise silently truncate.
- Prints the DEK manifest **before** the destructive step so the
  operator can `Ctrl-C` on a wrong-tenant-set surprise.
- Uses `pg_restore --single-transaction` so any failure mid-restore
  rolls the whole transaction back; the target DB never observes a
  partial restore.
- No outbound telemetry. No phone-home on restore completion.

## Retention pruning

`make backup-prune` deletes timestamped folders under
`s3://${S3_BUCKET}/${S3_PREFIX}/` older than `BACKUP_RETENTION_DAYS`
(default 30). It is meant to be run on a schedule (cron / scheduled
GitHub Action / etc.) so the bucket doesn't grow without bound, but the
operator runs it manually as needed.

The script only ever touches folders whose name matches the exact
backup.sh timestamp format (`YYYYMMDDTHHMMSSZ`). Anything else under
the prefix is logged as "unrecognized prefix, skipping" and left alone
-- the script will never delete a folder whose name it does not
understand.

### Safety gate

| Var                            | Required when    | Effect                                                                         |
|--------------------------------|------------------|--------------------------------------------------------------------------------|
| `DEPLOYAI_PRUNE_CONFIRM=YES`   | for any deletion | Without it the script runs DRY: lists the would-delete set, exits 0, no calls. |

The dry-run default mirrors `make restore`: a naive operator who runs
`make backup-prune` against the wrong bucket sees what *would* happen
before anything is destroyed. The script also refuses on `S3_BUCKET`
unset (exit 2) and on `BACKUP_RETENTION_DAYS` that is non-numeric or
`< 1` (exit 2).

### Required env vars

| Var                       | Required | Default               | Notes                                                          |
|---------------------------|----------|-----------------------|----------------------------------------------------------------|
| `S3_BUCKET`               | **yes**  | —                     | Script refuses to run unset.                                   |
| `AWS_ACCESS_KEY_ID`       | yes      | —                     | Standard AWS env. For MinIO use the `MINIO_ROOT_USER` value.   |
| `AWS_SECRET_ACCESS_KEY`   | yes      | —                     | Standard AWS env. For MinIO use the `MINIO_ROOT_PASSWORD`.     |
| `BACKUP_RETENTION_DAYS`   | no       | `30`                  | Positive integer; folders older than this many days are pruned.|
| `S3_PREFIX`               | no       | `deployai/backups`    | Must match the prefix `make backup` is writing under.          |
| `S3_ENDPOINT_URL`         | no       | (empty → real AWS)    | Set to `http://localhost:9000` for the dev MinIO container.    |
| `AWS_REGION`              | no       | `us-east-1`           | Forwarded to `aws s3 / s3api --region`.                        |

### Cron example

```cron
# Sundays at 03:00 UTC -- prune backups older than 30 days.
0 3 * * 0 cd /opt/deployai && DEPLOYAI_PRUNE_CONFIRM=YES make backup-prune
```

### Restore impact

`make restore` reads the timestamped folder you point `BACKUP` at.
**Folders deleted by `make backup-prune` cannot be restored from** --
they are gone from S3 and there is no soft-delete tier in this script.
Lower the cutoff (`BACKUP_RETENTION_DAYS=60`) or extend the retention
window before pruning if you need a longer recovery horizon.

### Prune security envelope

- Dry-run is the default. The destructive code path is only entered
  when `DEPLOYAI_PRUNE_CONFIRM=YES` is set in the environment.
- Refuses to run without `S3_BUCKET` (exit 2) so a missing prod env var
  fails loud rather than silently no-op'ing on a different default
  bucket.
- Refuses to run with `BACKUP_RETENTION_DAYS < 1` or non-numeric
  (exit 2) -- prevents a `BACKUP_RETENTION_DAYS=0` keystroke from
  becoming "delete every backup".
- Only deletes folders whose name parses as the exact backup.sh
  timestamp format. Any other prefix under `$S3_PREFIX/` (manual test
  uploads, mis-named objects, sibling tooling) is logged and skipped.
- Never deletes the bucket itself; only objects under
  `$S3_PREFIX/<ts>/`.
- No outbound telemetry. No upload of the deletion list anywhere.

## Railway production backups

The hosted stack runs on Railway (see
[`docs/ops/cloud-deploy.md`](./cloud-deploy.md)); Postgres data lives on
the `postgres-volume` volume mounted at `/var/lib/postgresql/data`.
Two layers, honestly stated:

1. **Railway volume backups** — the working automated layer. Configure in
   the dashboard: `postgres` service → the attached volume → **Backups** →
   enable a schedule (daily/weekly/monthly; each tier keeps its own
   retention). Backups are snapshots of the volume; restore is also
   dashboard-driven (pick a backup → restore — the service restarts on the
   restored volume). Do this **one-time setup now** if it isn't enabled;
   nothing in the repo can verify it for you.
2. **Manual `pg_dump` for offsite copies** — documented below, manual by
   design. There is currently **no scheduled dump-to-S3 automation** for
   Railway: the Fly-era nightly workflow (`.github/workflows/fly-backup.yml`
   → `scripts/fly-backup.sh`) was deleted/archived in the migration and has
   no Railway replacement yet (backlog ticket H1 remains open in that
   sense). Railway volume backups live in the same Railway account as the
   data — they protect against bad deploys and fat-fingered SQL, not
   account loss.

### Manual pg_dump over a TCP proxy

`railway connect postgres` opens an interactive psql session, which is not
scriptable for dumps. For a real `pg_dump` you need a TCP route to the
database. Postgres has no public ingress by default; enable one
deliberately, dump, then remove it:

1. Dashboard → `postgres` service → Settings → Networking → **TCP Proxy**
   → target port `5432`. Railway assigns a public `<host>:<port>` pair.
2. From your laptop (needs a local `pg_dump`; password is the
   `POSTGRES_PASSWORD` service variable, also in
   `~/.deployai-railway-state` if `scripts/cloud-standup.sh` set it up):

   ```bash
   pg_dump "postgresql://deployai:<PG_PASS>@<proxy-host>:<proxy-port>/deployai" \
     --format=custom --no-owner --no-privileges \
     -f "deployai-$(date -u +%Y%m%dT%H%M%SZ).dump"
   ```

3. Upload the dump wherever your offsite copies live (the compose-path
   S3 conventions above work fine), and **remove the TCP proxy** again if
   you don't want the DB port reachable from the internet (it is still
   password-authenticated, but the smaller surface is free).

Restore of such a dump follows the compose "[Restore
outline](#restore-outline)" above (`pg_restore --no-owner
--no-privileges`), pointed at the proxy instead of a local container, with
the same care: verify the dump is non-empty, know which tenant set you are
overwriting, and run Alembic afterwards if the app has advanced.

The archived Fly scripts
([`scripts/archive/fly-backup.sh`](../../scripts/archive/fly-backup.sh),
[`scripts/archive/fly-restore.sh`](../../scripts/archive/fly-restore.sh))
carry the safety patterns any future Railway automation should reuse:
dump-header verification before upload, the
`DEPLOYAI_RESTORE_CONFIRM` / `DEPLOYAI_RESTORE_FORCE_OVERWRITE` double
gate, DEK-manifest printout before the destructive step, and
single-transaction replay.

### DEK metadata

The compose path captures a tenant-DEK manifest alongside the dump. On
Railway, capture the same manifest manually when taking an offsite dump —
run it inside the control-plane container (`railway run` executes
*locally* and cannot reach `postgres.railway.internal`; `railway ssh`
runs in the deployed container):

```bash
railway ssh --service control-plane "python -m control_plane.cli.dek_metadata" > dek_metadata.json
```

(As always: `(tenant_id, name, dek_key_id)` tuples only — never the key
material itself.)

### What is NOT covered

- **MinIO/S3 artifact objects** (meeting audio uploads, email bodies when
  `ingest_email_body_mode=s3`): not in `pg_dump` and not on the Postgres
  volume. Ticket **H3** tracks artifact-bucket replication; until it
  lands, artifact blobs referenced by restored DB rows may be missing.
- **Redis**: the managed Redis has its own volume, but its contents
  (rate-limit counters, refresh sessions) are ephemeral by design — losing
  them logs users out, nothing more.
- **Secrets**: Railway service variables (`POSTGRES_PASSWORD`,
  `DATABASE_URL`, `DEPLOYAI_JWT_PRIVATE_KEY_B64`, OAuth client secrets)
  are not backed up by any of this on purpose. Keep them in your password
  manager (plus `~/.deployai-railway-state` / `~/.deployai-keys` from the
  standup script); a restore onto a fresh project requires re-setting them
  by hand.
