# 0001: Run locally without Docker

**Status:** Accepted, 2026-10-30

## Context

`CLAUDE.md` makes Docker Compose the reproducible local path, with PostgreSQL, Redis and MinIO. The development machine has no Docker, PostgreSQL or Redis, and has 7.6 GB of RAM. The app still has to run and be tested end to end here.

## Decision

Keep Docker Compose as the documented full stack, and add a second path, `scripts/run_local.py`, that needs only Python and Node.js:

| Concern | Docker path | Local path |
|---|---|---|
| Database | PostgreSQL container | Real PostgreSQL through `pixeltable-pgserver` |
| Background work | Celery and Redis | `ThreadPoolExecutor` in the API process |
| Files | MinIO | Local disk |

SQLite was rejected. The app relies on PostgreSQL features (`NUMERIC`, advisory locks, triggers, LangGraph's Postgres checkpointer), and tests should use the real database.

## Consequences

- Automated tests exercise the local path. The Docker path has not been run.
- All switches are settings (`TASK_EXECUTOR`, `STORAGE_BACKEND`), so the code above them is the same on both paths.
- Thread mode loses queued work if the API process dies. Durable state is in PostgreSQL, and the maintenance job restarts stuck runs, so the cost is a delay rather than lost work.
- `ENVIRONMENT=production` refuses `TASK_EXECUTOR=inline`, and `AUTH_MODE=dev`, so the shortcuts cannot reach production by accident. Thread mode is still allowed; do not use it for production.
