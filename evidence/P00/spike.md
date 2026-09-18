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
