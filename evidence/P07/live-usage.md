# P07 live usage evidence

- UTC: 2026-09-19T00:18 IST; real low-thinking Luna production call through the worker/API boundary returned call `7845b6d1-a37f-4241-9466-adcaa25e4e52`.
- PostgreSQL row: provider `openai-codex`, model `openai-codex/gpt-5.6-luna`, purpose `production`, outcome `succeeded`, 1,214 input tokens, 253 output tokens and 24 reasoning tokens; the call is linked to project `8fef982a-fc8f-4f74-a685-f0bdc71b5506`, run `e5bd6c8c-cf90-4f29-8e0e-638fe32a90b8`, task `ac77d19d-3b20-47c8-affa-17b5b88b9ec3` and attempt `6e774a59-893f-4d8c-a704-49fa433be650`.
- `ended_at` is present and `started_at <= ended_at`; task result refs contain the usage call ID. Project usage totals report one call with the same token totals and `estimated_cost: null`, `reported_billed_cost: null`.
- Limitation: no Codex/Copilot account quota snapshot was available; unknown monetary billing is intentionally not displayed as zero.
