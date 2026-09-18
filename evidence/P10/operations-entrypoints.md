# P10 operations entrypoint evidence

- UTC: 2026-09-18T19:23Z–19:24Z; delivered revision: `e15ceb1` plus Makefile target correction in the following working revision.
- `make backup` created `/home/naki/.config/shipyard/worktrees/ebookfactory/codex-ebook-factory-v2/var/backups/ebookfactory-20260918T192334Z.dump`; mode `600`, size `68206` bytes.
- `make --no-print-directory restore-check BACKUP=...` passed archive structure checks without creating or modifying a database.
- `make acceptance` ran the full verification suite and exited `2` with a redacted PARTIAL report naming Telegram credentials/live loop, Codex subscription image output, and isolated PostgreSQL restore. This is the intended honest failure state.
- Limitation: no user service lifecycle or isolated restore was attempted; the owner’s instruction forbids creating another database.
