# `make backup` — Postgres dump + tenant-DEK metadata

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
