# Telegram project switching live evidence

UTC: 2026-09-19T08:12:23Z  
Revision: `f2d614f`  
Database migration: `d4e5f6a7b8c9`

Live checks after migration and restart:

- All three user services are active and enabled under the `naki` user manager.
- `GET http://127.0.0.1:6969/ready` returned HTTP 200 with database status `ok`.
- Authenticated `/telegram/status` returned one configured chat, one configured sender, 27 linked projects, and one active project.
- PostgreSQL showed chat `6165158640` with 27 project links and exactly one active link.
- PostgreSQL showed migration head `d4e5f6a7b8c9`; `telegram_updates.processing_at` exists and the erroneous link-table claim column does not.
- A real owner message `Hi` was durably received as update `306086803`; its response outbox row was sent. The assistant response was also sent by the orchestrator outbox.
- `apps/api/tests/test_telegram.py`: 11 passed. Worker callback tests: 2 passed. Migration upgrade/rollback checks passed.
- The `/help` inline project keyboard, allowlisted callback switching, replay protection, callback acknowledgement, and all-project backfill are covered by focused boundary tests. No synthetic callback is claimed as a real owner click.

The Settings selector is catalog-backed: live `/providers/catalog` reported source `pi --list-models`, 15 models including `openai-codex/gpt-5.6-luna`; the persisted provider setting uses that model for orchestration.
