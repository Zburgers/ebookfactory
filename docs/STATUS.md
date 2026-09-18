# Build status

2026-09-18: P00 capability discovery, P01 runnable skeleton and P02 durable
jobs/events are implemented on the isolated branch. P01 revision `89673c6` provides the FastAPI health and
readiness service, pinned Python dependencies, shared JSON/OpenAPI contracts,
SQLAlchemy metadata and Alembic migrations. The owner-authorized PostgreSQL
target is `ebookfactory` with peer role `naki`; migrations are at head
`250e73df76d6` and the real readiness check returned `ok`. The P00 report at
`evidence/P00/capabilities.json` records Pi 0.85.1,
Codex CLI 0.155.0, rootless Podman 4.9.3 and PostgreSQL client 16.15. A real
Pi CLI probe returned usage fields from `openai-codex` / `gpt-5.5`; this is not
yet dashboard evidence. No Telegram credentials were supplied or
image-artifact route proven. P02 revision `a0ca026` adds hash-bound approval,
durable jobs, lease/fencing recovery, cancellation epochs, ordered event/outbox
replay, private worker callbacks and a minimal supervisor loop. Six focused
PostgreSQL recovery tests pass, including concurrent claim ownership; P03–P10
remain incomplete.

Next: P03 Pi sessions, provider settings and scoped tools. Pending owner input: Telegram token and
allowed chat/sender IDs. Pending technical proofs: Pi model gateway inside
containment, Codex subscription image bridge, provider quota availability,
maintained publishing converters, and the rest of the integrated product.

Operating instruction: for future probes and delegated work, explicitly select
the least-cost available route, preferably GPT 5.6 Luna low when the runtime
actually exposes it; record the selected model/effort and never infer it from
a catalog name.

Maintain this as a short current-state summary; preserve activity history in AGENT_LEDGER.md.
