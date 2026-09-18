# Build status

2026-09-18: P00 capability discovery implemented on the isolated branch. The
redacted report at `evidence/P00/capabilities.json` records Pi 0.85.1,
Codex CLI 0.155.0, rootless Podman 4.9.3 and PostgreSQL client 16.15. A real
Pi CLI probe returned usage fields from `openai-codex` / `gpt-5.5`; this is not
yet dashboard evidence. No database target was changed, Telegram credentials
were supplied, or image-artifact route was proven. P01–P10 remain incomplete.

Next: P01 runnable skeleton and shared contracts. Pending owner inputs:
exact PostgreSQL target approval and Telegram token/allowed IDs. Pending
technical proofs: Pi model gateway inside containment, Codex subscription image
bridge, provider quota availability, maintained publishing converters.

Operating instruction: for future probes and delegated work, explicitly select
the least-cost available route, preferably GPT 5.6 Luna low when the runtime
actually exposes it; record the selected model/effort and never infer it from
a catalog name.

Maintain this as a short current-state summary; preserve activity history in AGENT_LEDGER.md.
