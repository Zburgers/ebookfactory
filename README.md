# Ebook Factory v2

Status: DESIGN HANDOFF / NOT IMPLEMENTED. This folder contains the approved product design, implementation scaffold, and build-agent instructions. No application, database, credentials, or containers were provisioned by this handoff.

A private ebook production system: discuss an idea with one orchestrator, approve a brief, let durable production jobs research/write/edit, review the manuscript and art, then download a publishing package. Fiction and nonfiction share a document core. Dashboard is primary; Telegram is a second channel to the same conversation.

## Start here

1. [Agent rules](AGENTS.md)
2. [Product and architecture](docs/DESIGN.md)
3. [Contracts and recovery](docs/CONTRACTS.md)
4. [Provider, usage, and image integration](docs/INTEGRATIONS.md)
5. [Publishing acceptance](docs/PUBLISHING.md)
6. [Build packets](docs/plans/2026-09-18-build.md)
7. [Scoring and mandatory gates](docs/ACCEPTANCE.md)
8. [Goal prompt](docs/GOAL_PROMPT.md)
9. [Append-only agent ledger](docs/AGENT_LEDGER.md)
10. [Sources and reuse map](docs/REFERENCES.md)

## Scaffold map

`apps/api/` owns the domain, persistence, scoped tools, exports, Telegram, and replayable events. `apps/worker/` owns Pi sessions and the supervised execution boundary. `apps/web/` owns the dashboard using existing UI components. `packages/contracts/` contains wire schemas; `packages/prompts/` contains versioned book profiles. `infra/` contains migrations, Podman execution, and service setup. `scripts/` and `evidence/` hold reproducible checks and redacted results.

These are planning scaffolds, not claims that their runtime implementations exist. Read each directory README for intended files. Do not copy the legacy project into this tree.

## Scope and open inputs

- Personal use only. Reliability matters; tenancy, billing customers, and scaling do not.
- Pi is the orchestrator runtime. Global Pi catalog/auth reuse is allowed; global extension and tool discovery is not automatically allowed.
- PostgreSQL queue is approved. Exact existing server/database/role must be confirmed by the owner before migrations/provisioning. Read-only discovery may proceed.
- Telegram token plus allowed chat/user IDs must be configured locally; never commit them.
- Codex subscription image capability is requested. Its unattended callable route must be proven; manual art import is a fallback, not fulfillment of automated art.
- Delivery requires completion score >90/100 (at least 91) AND every mandatory gate. All target functionality remains in scope even if the score crosses 90.
- No Amazon account upload or publication is authorized by this handoff.

Runnable entry points are `make doctor`, `make dev`, `make install-service`, `make start`, `make verify`, `make acceptance`, `make backup`, and `make restore-check BACKUP=...`. `make acceptance` intentionally exits with PARTIAL until every external hard gate is evidenced; it never weakens the rubric.
