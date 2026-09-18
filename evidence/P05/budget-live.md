# P05 live budget-block evidence

- Code revision: `e68807f`; UTC: `2026-09-18`.
- Against native PostgreSQL `ebookfactory`, the real API flow created a
  synthetic brief, approved it with `max_turns: 0`, claimed it through the
  private worker endpoint, then submitted a production result carrying one
  input and one output token.
- The production-result boundary returned HTTP 409 with
  `production budget blocked: max_turns_exceeded`. PostgreSQL shows project,
  run, task and job state `blocked`, job error `budget_exceeded`, and attempt
  state `failed`. Events are `run.approved`, `job.claimed`, `job.blocked`.
- Artifact query for the run returned zero rows. No provider/model turn was
  invoked and no credits were consumed; this proves rejection before
  publication, not provider-side billing behavior.
