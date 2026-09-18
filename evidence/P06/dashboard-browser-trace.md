# P06 interactive dashboard evidence

- Code revision: `e37c2ae` (dashboard behavior from `530de4e`). Runtime:
  Chromium 153, API `http://127.0.0.1:18082`, native PostgreSQL 16 database
  `ebookfactory` through peer role `naki`.
- Synthetic project `2c8daff2-9f20-47a2-b5c7-16cf279d7321` was created through
  the dashboard. The trace submitted a conversation message, created a brief,
  displayed its exact hash, approved it, and then cancelled the queued run
  `6fd30fd1-5767-4937-b49e-ec7e91253097` during cleanup. No model call ran.
- The trace seeded one synthetic section, edited it in the dashboard, and the
  database verified two immutable section revisions. The review panel showed a
  synthetic finding and the event timeline grew from one to four entries.
- Export from the edited revision produced links for `book.md`, `cover.jpg`,
  `book.epub`, `book.docx`, `book.pdf`, `metadata.json`, `metadata.csv`,
  `sources.json`, `manifest.json` and `validation.json`. A browser fetch of the
  rendered `book.md` download returned HTTP 200. Persisted export revision
  `d7c5f819-c4dc-4491-94a6-a133491592ba` has immutable artifact records under
  `var/artifacts/exports/d7c5f819-c4dc-4491-94a6-a133491592ba/`.
- Usage navigation displayed the real Codex quota rows; Settings displayed the
  explicit unconfigured Telegram state. The trace found labeled controls,
  live regions and non-empty button labels suitable for keyboard operation.
- Limitation: this proves the local dashboard journey and download boundary,
  not authentication, Telegram delivery, worker restart-through-production,
  or a live provider response initiated by the dashboard.
