# P02 integration evidence

- Code revision: `a0ca026`
- UTC: 2026-09-18T17:36:59Z–17:39Z
- Target: owner-authorized native PostgreSQL 16.15, database `ebookfactory`, peer role `naki`, Unix socket `/var/run/postgresql`; no password used
- Real database behavior: `scripts/tests/test_recovery_postgres.sh` loaded the ignored local `.env` and passed 6 PostgreSQL tests; the focused health plus recovery run passed 11 tests
- Covered behavior: atomic hash-bound approval and dedupe, concurrent `FOR UPDATE SKIP LOCKED` single-owner claim, lease heartbeat, checkpoint persistence, expiry/reclaim generation fencing, stale completion rejection, cancellation epoch rejection, pause/resume, bounded retry, ordered event replay and outbox rows
- Private boundary: worker claim/heartbeat/checkpoint/complete/fail and run-cancel endpoints require `X-Ebook-Worker-Token`; wrong-token behavior returned HTTP 401 without exposing the configured token
- Worker: `apps/worker/src/supervisor.ts` contains a cancellable private-API polling loop; it does not yet create Podman jobs
- Verification: `make verify` passed; its ordinary pytest run reports 5 passed and 6 DB-test skips without exported test env, while the dedicated recovery target passed all 6 against PostgreSQL; migration rollback/upgrade reported 20 tables and contract generation passed
- Host checks: peer query returned `naki | ebookfactory`; rootless Podman reported `true` and runtime `runc`
- Cleanup: the recovery fixture reported zero remaining `recovery-*` projects after the run
- Limitation: P03–P10 provider, scoped tools, containment, production, dashboard, usage, art, publishing, Telegram and backup gates remain unimplemented; no hard gate is claimed
