# P07 Codex quota evidence

- UTC observation: `2026-09-18T19:36:44Z`.
- A read-only Codex app-server `account/rateLimits/read` probe returned three
  subscription records. It did not start a model turn or consume account
  credits.
- The real PostgreSQL `ebookfactory` database contains the redacted rows:
  `primary-300m` at 30% used / 70% remaining, `secondary-10080m` at 26% used /
  74% remaining, and a credits record with no percentage/window data marked
  `unavailable`. The plan label is `plus`; the account is represented only by
  the neutral alias `subscription`.
- `apps/worker/src/quota.ts` parses the provider response without retaining
  provider account identifiers. `POST /private/quota/snapshots` requires the
  local worker token, and `GET /quota` returns recent observations with stale
  supported windows marked explicitly. The dashboard Usage view displays the
  same states and continues to show monetary billing as unknown.
- Focused quota tests, the production boundary test and the final full
  `make verify` passed at delivery revision `530de4e`.
- Limitations: this proves Codex subscription-window visibility only. It does
  not prove Copilot quota, provider billing, or a paid image-generation turn.
