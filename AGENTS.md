# Build-agent contract

Read README.md, docs/DESIGN.md, docs/CONTRACTS.md, docs/INTEGRATIONS.md, docs/PUBLISHING.md, docs/plans/2026-09-18-build.md, and docs/ACCEPTANCE.md before implementation. The latest explicit owner instruction takes precedence.

## Roles and work

- Lead: GPT 5.6 Luna high/xhigh; owns integration, contracts, reviews, and completion evidence.
- Implementers: GPT 5.6 Luna low for bounded packets with named files and acceptance criteria. Raise reasoning for difficult recovery/security work.
- Critics: separate GPT 5.6 Luna high sessions; inspect the delivered revision and reproduce failures. Never approve their own implementation.
- If the requested model/reasoning or spawning feature is unavailable, record it. Never invent agent identities or independent review. Use sequential work but mark independent critique unfulfilled.
- Lead initializes local Git after checking the directory; use isolated worktrees for parallel edits. Commit coherent reviewed packets. No push, PR, or remote deployment unless requested.
- Existing Ebookmaker and MuMuAINovel are reference directories. Preserve them and any unrelated database/service/container.
- Use Context7 for SDK/library specifics and official sources for provider and KDP behavior. Pin versions actually verified. Do not infer runtime capabilities from a catalog name.

## Implement / critique loop

1. Read the assigned packet, actual callers, and contracts. Name the smallest observable success.
2. Implement it and run a focused behavior check. Integration evidence must exercise the real boundary, not only doubles.
3. Append one concise implementation ledger row with paths/revision, result and reason.
4. A critic examines the same revision, writes findings/evidence, and appends one concise critique row with confidence and reason.
5. Lead resolves critical/high findings; iterate, preserving previous rows. Recheck affected behavior after changes.
6. Update docs/STATUS.md and docs/SCORECARD.md from evidence. A passing unit suite is not a passing product.
7. Finish only under docs/ACCEPTANCE.md. If an external credential/capability blocks completion, deliver working independent portions and state PARTIAL/BLOCKED without inflating the score.

## Ledger

Only the lead appends to docs/AGENT_LEDGER.md to avoid concurrent rewrites; subagents return a proposed row. One row at the end of each agent assignment, plus a final lead row. One or two short lines each; no chain-of-thought, full logs, secrets, or transcript dumps. Include UTC, actual agent ID, role/model/effort, packet, revision/evidence, outcome, confidence and short reason. Confidence is subjective evidence confidence, not completion percentage. Count distinct actual agent IDs. Corrections are new rows; never edit old rows. Git history supplies an audit trail; this is not claimed as a tamper-proof log.

## Product invariants

- Only the main orchestrator speaks to the owner. Child tasks return artifacts/results.
- Approval binds a specific brief or manuscript revision. Do not silently reinterpret it.
- Work survives closed tabs and restarts through DB jobs/checkpoints; no in-memory-only production queues.
- Pi is not the source of truth for book state; approved document revisions in PostgreSQL are.
- Host chat has project tools only; no arbitrary host shell, global skills/extensions, or unscoped MCP tools.
- Rootless Podman execution uses private job storage, limited resources, scoped credentials and fenced publication. Do not mount home, DB credentials, or a container socket into jobs.
- Global Pi catalog/auth reuse is allowed. Never log credentials, overwrite unrelated global settings, or mount the global harness into untrusted execution.
- Report provider usage, estimates and unknowns separately. Never display unknown billing as free.
- No placeholders labelled as finished manuscripts/images/exports. No `.pdf`/`.epub` extension tricks.
- Exact PostgreSQL target still needs owner confirmation; do independent work first. Telegram setup waits for the actual token/chat IDs.
- No public deployment, Amazon publication, automatic purchases, account-credit consumption, or destructive shared-resource cleanup.

## Minimal engineering

Reuse maintained UI components and renderers; do not build a chat design system. Reuse MuMu's domain patterns before inventing equivalents. Inspect and attribute direct source reuse; do not casually strip GPL notices. Avoid speculative frameworks, Redis, vector databases, and arbitrary multi-agent recursion. Meaningful checks are required for job recovery, fencing, isolation, artifact validity and usage accounting.
