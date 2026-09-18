# P07 usage drill-down evidence

- Code revision: `e68807f`; UTC browser/API observation:
  `2026-09-18T19:51:04Z`; Chromium 153 against the native PostgreSQL-backed
  API on `127.0.0.1:18082`.
- The real project `Luna Low Usage Demo` displayed one persisted call in the
  Usage view: provider/model `openai-codex/openai-codex/gpt-5.6-luna`, outcome
  `succeeded`, 1,214 input tokens and 253 output tokens. The call ID was
  displayed and the response was fetched through `GET /usage/calls` scoped to
  the project.
- The call detail explicitly rendered `billing unknown`; the summary rendered
  `estimated_cost: unknown` and `reported_billed_cost: unknown`. The same view
  displayed the real primary/secondary quota windows and the unavailable
  credits state.
- Unit/API coverage: `tests/test_usage.py` covers lineage and project scoping;
  full verification passed with 20 tests passing and 9 optional PostgreSQL
  tests skipped when their separate test-database variable is unset.
