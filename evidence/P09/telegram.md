# P09 Telegram adapter evidence

- UTC: 2026-09-18T19:47Z–19:49Z; delivered revision: `ba181f7`.
- Scope: durable allowlisted update receipt, project link, same-conversation message routing, revision-bound `/approve`, `/projects`, `/use`, `/status`, `/pause`, `/resume`, `/cancel`, retryable outbox, HTTPS Bot API client, and redacted status API.
- Focused behavior: `uv run --directory apps/api pytest -q tests/test_telegram.py` — 2 passed; replayed update produced one durable message and bounded outbox state.
- Migration: owner-authorized PostgreSQL `ebookfactory` advanced from `3c2a5f8e1b4d` to `8b4e6c7d9a10`; SQLite upgrade/downgrade/upgrade check passed with 24 tables.
- Live local smoke: `GET /telegram/status` returned `configured:false`, zero allowlisted IDs and zero linked chats; an unconfigured private update returned `accepted:false`, `reason:"telegram_not_configured"`. The synthetic update and cursor row were removed afterward.
- Full verification: `make verify` passed — 15 ordinary tests, 9 PostgreSQL recovery tests, migrations, contracts, worker/web, sandbox and containment checks.
- Limitation: no Telegram token or allowed chat/sender IDs were supplied, so the actual Telegram loop, sender rejection in a real chat, reconnect and delivery retry remain unpassed. No token or chat identifiers are stored in this evidence.
