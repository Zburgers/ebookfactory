# Telegram live audit

Observed 2026-09-19 UTC with all three user services active.

- Telegram configuration endpoint reported configured, one allowed chat, one
  allowed sender, one linked chat, and durable cursor `306086802`.
- PostgreSQL contains one processed update (`306086801`) from chat/sender
  `6165158640`, corresponding to the earlier `/help` receipt.
- PostgreSQL contains **zero** messages with `channel='telegram'`; no owner
  free-text Telegram message has been observed or fabricated.
- The current link is chat `6165158640` -> project
  `b6010f6f-1104-4f6e-a779-33b85de7dfab` (`Live outline handoff verification`).
  It is not automatically the dashboard project selected by the owner.
- After the reviewed service restart, the Telegram worker remained active. The
  journal showed only earlier transient HTTP/timeout poll errors; no pending
  update or durable routing failure is currently present.

H5 remains open until the owner sends a real message from the allowlisted
Telegram account to `@nakiskindlerbot`, after linking the intended project with
the dashboard Settings action or `/use PROJECT_ID`. The resulting inbound
message, orchestrator response, dedupe behavior and project conversation ID
must then be recorded here without exposing credentials.
