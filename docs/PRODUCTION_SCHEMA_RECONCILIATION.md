# Production Schema Reconciliation Runbook

This runbook preserves existing data and manually aligns a production PostgreSQL schema with the current SQLAlchemy models.

## 1) Preconditions

- Keep your existing mounted volume (especially `/config/postgres`) when deploying updates.
- Schedule a maintenance window.
- Ensure you can run commands inside the running app container.

## 2) Backup First (Required)

Create a full logical backup **before** any schema change.

Example pattern:

- `docker exec <app_container> pg_dump -U <db_user> <db_name> > backup_YYYYMMDD_HHMM.sql`

Validate backup file exists and is non-zero.

## 3) Generate Exact Reconciliation SQL (from live DB)

Use the generator script in this repo:

- [scripts/generate_schema_reconcile_sql.py](scripts/generate_schema_reconcile_sql.py)

Run (from repo root, using app venv/interpreter):

- `/Users/rich/Dev/hmm-local/.venv/bin/python scripts/generate_schema_reconcile_sql.py`

Optional explicit output path:

- `/Users/rich/Dev/hmm-local/.venv/bin/python scripts/generate_schema_reconcile_sql.py --output /tmp/hmm_reconcile.sql`

What it does:

- Diffs live PostgreSQL schema against current SQLAlchemy metadata.
- Emits idempotent SQL for missing tables/columns/indexes.
- Never drops data.

## 4) Review SQL Before Apply

Review generated file carefully:

- Confirm no unintended table/column names.
- Look for `TODO` comments about columns added as nullable (non-null with no default).
- Confirm index names and table names are expected.

## 5) Apply SQL

Run inside PostgreSQL context (example):

- `psql -U <db_user> -d <db_name> -f /tmp/hmm_reconcile.sql`

If using containerized execution, copy/mount the SQL file and apply via `docker exec`.

## 6) Restart + Validate

After apply:

1. Restart app container.
2. Validate health endpoint:
   - `curl http://<host>:8080/api/operations/status`
3. Check logs for scheduler/model errors.

## 7) Rollback Plan

If needed:

- Stop app.
- Restore backup to PostgreSQL.
- Restart app on known-good image/tag.

## Notes

- This process is safe for data retention when the same `/config/postgres` volume is retained.
- The generator is designed to create an exact SQL plan for the **current live schema** at generation time.
