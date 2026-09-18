# P03 integration evidence

- Code revision: `8de7198`
- UTC: 2026-09-18
- PostgreSQL migration: owner target `ebookfactory` / peer role `naki` is at `3c2a5f8e1b4d`; provider `(provider, scope)` uniqueness is applied
- Behavior checks: the full API suite passed 7 non-DB tests plus 7 PostgreSQL recovery/conversation tests; the focused combined run passed 14 tests; worker modules passed Node syntax verification
- Conversation boundary: project creation creates a primary dashboard conversation; inbound messages are sequence-locked and replayed external IDs return the original durable message; cross-conversation dedupe reuse is rejected
- Provider boundary: only endpoint/protocol/model metadata and a credential reference are persisted; provider URLs containing userinfo/query strings are rejected; provider GET responses expose only a boolean credential-configured state; connection-test behavior is recorded separately in `evidence/P03/provider-connection.md`
- Capability boundary: HMAC tokens bind project, job, fencing generation, tool name and expiry; wrong project/generation/tool is rejected; the only enabled scoped tool is `get_job_status`
- Pi boundary: `apps/worker/src/pi.ts` builds explicit `--no-extensions --no-skills --no-prompt-templates --no-tools --no-session` CLI arguments; no inherited global tools or prompts are loaded
- Verification: `make verify` passed; its normal pytest run reports 7 passed and 7 DB-test skips without exported test env, while the dedicated PostgreSQL target passed 7 DB tests; contract generation, migrations and worker syntax checks passed
- Limitation: no dashboard UI, live dashboard-configured provider response, Pi SDK session persistence, auth/reconnect flow, usage capture or production tool beyond status lookup is claimed yet
