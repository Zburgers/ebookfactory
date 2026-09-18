# P01 integration evidence

- Code revision: `89673c6` (includes implementation revision `050be81`)
- UTC: 2026-09-18T17:19:26Z
- Target: owner-authorized native PostgreSQL 16.15, database `ebookfactory`, peer role `naki`, Unix socket `/var/run/postgresql`; no password used
- Migration command: `uv run --directory apps/api alembic -c <repo>/alembic.ini upgrade head`
- Migration result: PostgreSQL context applied revisions `74fba9d42191` and `250e73df76d6`; public table count `20`; both project relationship foreign keys are present
- Isolated rollback check: SQLite `upgrade head -> downgrade base -> upgrade head`; required tables present and `20` tables reported
- API boundary: Uvicorn on `127.0.0.1:18080` returned `/health` HTTP 200 and `/ready` HTTP 200 with database status `ok`; process shut down cleanly with Ctrl-C
- Contract output: `packages/contracts/openapi.json` parses; generated TypeScript contains `HealthResponse` and `ReadinessResponse`
- Dependency lock: `apps/api/uv.lock` pins verified Python 3.14-compatible versions
- Security check: no known credential-pattern matches in tracked source/evidence; `.env` remains ignored and contains no password
- Limitation: the dashboard, durable job behavior, worker, sandbox, production, Telegram, publishing, art and backup gates remain unimplemented
