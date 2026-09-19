# Live editorial review-stage run

Date: 2026-09-19 (Asia/Kolkata)

This disposable run exercised the enabled systemd API/worker against PostgreSQL
and the configured `openai-codex/gpt-5.6-luna` provider with no art direction,
so the editorial graph was tested independently of the image subprocess.

- Project: `328ade64-5f82-4be8-8ef4-9f49400f0c42`
- Run: `90cc4ac9-128b-46d3-94c5-e7be4ed6291f`
- Task order and final state: `outline=succeeded`, `production=succeeded`,
  `review=succeeded`; run/project=`draft_review`.
- Durable artifact: `90cc4ac9-128b-46d3-94c5-e7be4ed6291f/book.md`, 5,017 bytes,
  SHA-256 `7d1642a2eced661b3d65ffe4e08090d331427611bc3002128b59d1d0b46a6b0e`,
  validation state `generated`.
- Usage rows: outline `1185/284`, production `1512/1007`, review `2708/422`
  input/output tokens; all three report provider `openai-codex` and model
  `openai-codex/gpt-5.6-luna`. No subscription billing amount was fabricated.
- Review result began with `PASS` and was persisted on the review task.

This proves the ordered outline → manuscript → review handoff at the real
database/worker/provider boundary. It does not by itself satisfy the separate
50–150-page acceptance gate.
