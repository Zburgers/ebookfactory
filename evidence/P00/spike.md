# P00 spike summary

- UTC: 2026-09-18T16:50:36Z
- Checkout: `/home/naki/.config/shipyard/worktrees/ebookfactory/codex-ebook-factory-v2`
- Probe: `pi --no-tools --no-extensions --no-skills --no-prompt-templates --no-session --mode json --print`
- Result: exit 0; response token `P00_SPIKE_OK`
- Provider/model: `openai-codex` / `gpt-5.5`; API `openai-codex-responses`
- Final observed usage: input 1004, output 27, reasoning 16, total 1031
- Billing interpretation: the adapter exposed a cost field, but actual subscription billing is unknown and is not asserted
- Security: raw JSONL/session output was not stored; it contained session IDs and encrypted provider metadata
- Codex: `codex-cli 0.155.0`; app-server help is available; unattended image artifact creation remains unverified
- Podman: `4.9.3`; rootless field verified true
- PostgreSQL: client `16.15`; exact target not selected or changed
- Telegram: unconfigured; no token/chat IDs tested

## Follow-up capability probe

- UTC: 2026-09-18T20:53:53Z
- Command boundary: `pi --no-extensions --no-skills --no-prompt-templates --no-tools --no-session --mode json --print --thinking low --model openai-codex/gpt-5.6-luna`
- Result: exit 0; exact response `PING`; no tools, extensions, skills, prompt templates or session persistence were enabled.
- Provider/model/API: `openai-codex` / `gpt-5.6-luna` / `openai-codex-responses`
- Final observed usage: 1,377 input tokens, 5 output tokens, 0 reasoning tokens, 1,382 total tokens.
- Billing interpretation: the response exposed an API-equivalent cost field, but actual subscription billing remains unknown and is not asserted.
- Limitation: this is a direct trusted-host Pi capability probe, not yet a dashboard-configured H1 call.
