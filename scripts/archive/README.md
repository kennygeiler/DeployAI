# scripts/archive — superseded operational scripts

Kept for reference, not wired to anything. Do not run against current
infrastructure without reading the note below.

## `fly-backup.sh` / `fly-restore.sh` (archived 2026-08-11)

Fly.io-era production backup/restore (pilot-refresh ticket H1): `pg_dump`
inside the Fly Postgres machine over `fly ssh console`, gzip + upload to
S3/Tigris, and the double-gated restore through `fly proxy`. The nightly
workflow that drove them (`.github/workflows/fly-backup.yml`) was deleted in
the Railway migration.

On Railway the equivalent posture is:

- **Railway volume backups** for the Postgres volume (scheduled in the
  dashboard) — see the "Railway production backups" section of
  [`docs/ops/backup.md`](../../docs/ops/backup.md).
- A **manual `pg_dump` over a Railway TCP proxy** for offsite copies —
  documented (not scripted) in the same section.

The safety patterns in these scripts (dump-header verification,
`DEPLOYAI_RESTORE_CONFIRM` / `DEPLOYAI_RESTORE_FORCE_OVERWRITE` double gate,
DEK-manifest printout before the destructive step, single-transaction replay)
are the reference for any future Railway backup automation. The compose-stack
siblings (`scripts/backup.sh`, `scripts/restore.sh`, `scripts/backup-prune.sh`)
remain live and unchanged.
