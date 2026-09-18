# P05 budget-blocking evidence

- UTC: 2026-09-18T19:55Z–19:58Z; delivered revision: `f04fd56`.
- `apps/api/app/budget.py` checks persisted `max_turns`, `max_input_tokens`, `max_output_tokens`, `max_total_tokens`, and `max_seconds` against prior normalized usage and the current fenced attempt.
- Exceeded work transitions the fenced job, task, run and project to `blocked`, clears the lease, records `budget_exceeded`, and emits `job.blocked` before production output acceptance.
- Focused behavior: `uv run --directory apps/api pytest -q tests/test_budget.py` — 1 passed.
- Full verification: `make verify` passed — 16 ordinary tests, 9 PostgreSQL recovery tests, migrations, contracts, worker/web, sandbox and containment checks.
- Limitation: no additional provider call was spent solely to trigger a live budget rejection; the hard production budget subcriterion remains unawarded until that boundary is exercised in an owner-approved run.
