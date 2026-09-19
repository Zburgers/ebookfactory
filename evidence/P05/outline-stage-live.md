# Live durable outline-stage evidence

Date: 2026-09-19 (Asia/Kolkata)

The enabled rootless worker completed a real two-task PostgreSQL run after the
outline-stage packet was implemented.

- Project: `b6010f6f-1104-4f6e-a779-33b85de7dfab`
- Run: `1f662f54-be44-4c7c-84a0-163ddfc4f975`
- Durable tasks: `outline:succeeded`, `production:succeeded`
- Final project state: `draft_review`
- Outline result: persisted in the outline task and exposed by the fenced
  production context endpoint
- Manuscript artifact: `book.md`, 9,580 bytes, SHA-256
  `afa4f9fb867d752867fe9df3fa83ef8c76755e13742e437e13afd158042f13b8`
- Persisted section revisions: 9
- Usage calls: outline `1189` input / `396` output; production `1627` input /
  `1758` output
- Provider/model for both calls: `openai-codex` /
  `openai-codex/gpt-5.6-luna`

This proves the durable outline handoff and live usage lineage. It does not
claim a 50–150 page provider run, browser-close recovery, or the complete
research/review/publishing graph; those remain acceptance work.
