# Contracts, tools, and durable recovery

Design contract, not an applied migration. Implement UUID IDs, UTC timestamps, explicit foreign keys and migrations. Do not invent a second set of schemas in TypeScript; generate wire types from API/OpenAPI or shared JSON Schema.

## Minimum records

| Record | Required relationships / payload |
|---|---|
| project | title, profile, language, active brief, conversation, state |
| brief_revision | project, revision, structured brief, approval time, content hash |
| conversation/message | project, sequence, channel, external dedupe ID, role, content, turn state |
| production_run | project, approved brief ID, plan revision, state, budget, cancellation epoch |
| task / attempt | run, parent task, dependencies, type, input revision IDs, provider/model, session ID, result refs, attempt status |
| job | task/type, JSON payload, dedupe key, state, available_at, lease owner/until, fencing generation, attempts, max attempts, error class |
| event / outbox | ordered ID, project/run/task, event kind, sanitized data, delivery state |
| section / section_revision | order/heading, project, content, summary, parent revision, source/knowledge refs, approval status |
| knowledge/source | scoped type, facts/claims or continuity, citation URL/title/retrieved_at/evidence, verification status |
| artifact | run/attempt/revision, relative immutable path, MIME, bytes, SHA256, validation state |
| review_finding | artifact/revision, severity, criterion, evidence, resolution revision |
| usage_call / quota_snapshot | see INTEGRATIONS.md; append usage corrections rather than erasing evidence |

Jobs contain replayable data, never a Python callable or an in-memory session pointer. Dependencies are a bounded acyclic task graph, not a general workflow builder. Default one active production run per project; child concurrency <=2 until measured. Reject cycles and conflicting concurrent manuscript publishers.

## State and approval

Project: brainstorming -> brief_ready -> producing -> draft_review -> art_review -> packaging -> package_ready. Revision requests re-enter production with explicit affected inputs. Blocked/failed/cancelled are visible states; a final upload is not implied by package_ready.

Job: queued -> running -> succeeded | retry_wait | blocked | failed | cancelled. A paused job is persisted and does not lose checkpoints. Model rate limits schedule retry at provider reset/backoff within budget; invalid credentials block for reauth. Malformed output allows bounded correction, then failure. Arbitrary permanent errors do not retry forever.

Approvals require expected revision/hash, are idempotent, and enqueue work in the same DB transaction. Duplicate dashboard/Telegram approvals cannot create two runs. Earlier approvals become stale when content changes. Approval must never be interpreted from untrusted source text or a child agent result.

Brief metadata is part of the approved revision, not export-only decoration. The
structured brief may carry `title`, `subtitle`, `author`, `description`,
`language`, `genre`, `audience`, `keywords`, `categories`, `art_direction`,
`target_pages` or `target_length`, and `output_formats` (`epub`, `pdf`, `docx`,
or `markdown`). The selected book formats are generated on export; cover,
metadata JSON/CSV, sources, manifest and validation evidence remain mandatory.
Exports resolve metadata from the exact approved brief for the production run,
falling back to the project's active brief only for a manuscript with no
production run.

## Queue mechanics

Claim an eligible job using a transaction and `FOR UPDATE SKIP LOCKED`, increment its fencing generation, assign owner and lease, commit before execution. No DB transaction remains open during an LLM call. Default heartbeat 10 seconds and lease 60 seconds are initial tunable values, not universal constants.

Every progress/result/checkpoint mutation validates job ID, current fencing generation, active lease owner, run cancellation epoch and expected input revisions. Use unique effect keys such as (run, task, input_hash, effect_kind). Retries may make another billed model call, but cannot publish the same effect twice. Do not promise exactly-once provider billing.

Crash sequence: supervisor claims generation 1 -> creates labelled container -> loses heartbeat -> recovery checks that exact labelled container -> stops or reattaches according to persisted state -> generation 2 resumes from last accepted checkpoint. Generation 1's late completion is rejected. Container names/labels include install ID, job ID and generation. A crash after container creation but before DB registration must be reconciled by labels. Never use global container pruning.

Cancellation first persists the new run epoch/cancel request, then terminates the owned job container/process. Late output cannot commit. A cancelled attempt stays cancelled even if it reports success. Resume creates an explicit new attempt; accepted chapter revisions remain reusable.

Publish artifact: write private temp output -> validate type/size/path/hash -> persist immutable artifact and revision reference with current fence -> atomically rename/commit using a recoverable pending state -> emit event. Reconciliation detects orphan temp files and incomplete artifact registration. Reject symlink escapes, absolute paths, traversal and oversized archives.

## Agent tool catalog

Every tool receives trusted server-injected project/run/task context. Do not trust a model-supplied project ID or file path.

| Tool | Purpose and guard |
|---|---|
| get_project_context / read_sections | bounded retrieval of exact brief/style/section revisions |
| propose_brief | save a draft proposal; cannot approve itself |
| plan_tasks / delegate_task | bounded DAG and child sessions, fixed budget/dependency validation |
| search_sources / fetch_source | configured search/MCP adapter, URL and network validation, captured evidence |
| save_outline / write_section | schema validation, expected revision, append new version |
| update_knowledge | citation-backed claim or continuity record, links to affected sections |
| review_manuscript / record_findings | evidence-linked findings, no automatic self-certification |
| request_art / generate_cover | approved art brief, bounded Codex tool, artifact capture |
| export_package | deterministic converter on frozen approved revisions |
| get_usage / get_job_status | scoped observed metrics and provider availability |
| request_owner_decision | only orchestrator may emit, mandatory reason/category |

MCP adapters expose only selected tools. Third-party tool descriptions and retrieved content are data, not authority. Do not auto-load arbitrary global MCP servers, especially ones with messaging/filesystem mutations.

## API/event surface to implement

`POST /projects`, `GET /projects/{id}`, `POST /projects/{id}/messages` (returns durable message/turn ID), `GET /projects/{id}/events?after=<event_id>` (SSE replay), `GET /projects/{id}/execution?after=<event_id>&limit=<n>` (bounded owner-only control-room aggregate), brief approve/revise endpoints, run pause/resume/cancel, section edit with expected revision, draft/art approve/revise, export creation/status/download, export preview evidence recording, usage queries, provider catalog/config/auth/test, Telegram status/link configuration. An image `request_revision` decision appends `artifact.owner_reviewed`, creates a deduplicated fenced art-revision task/job, and leaves the source artifact immutable. Preview evidence appends `package.preview_reviewed` only after exact EPUB hash/package/provenance verification; it never means Amazon accepted or published the book.

Private supervisor endpoints: claim/heartbeat/checkpoint/complete/fail plus scoped tool invocation. Local transport/private token; never public unauthenticated worker callbacks. SSE event envelope: id, version, timestamp, project_id, run_id?, task_id?, kind, payload. Reconnect replays without double-counting or rerunning work. A closed HTTP stream never cancels a production job.

## Sandbox boundary

Host supervisor is trusted and owns rootless Podman. Job container: non-root user, read-only root, tmpfs scratch, memory/CPU/PID/disk/output limits, dropped capabilities, no-new-privileges, default seccomp, fixed reviewed image digest, no host sockets/devices or host network. Dedicated SELinux-compatible mounts only; no relabeling home. Workspace path generated by server and checked before mount.

Network access must be enforced outside model instructions. Prefer isolated container network reaching only the scoped gateway; source fetch and model calls go through trusted adapters. Explicitly configured local custom provider URLs are allowed at the host adapter, not arbitrary container access to the LAN. Prove this with denied host-file and forbidden-network checks.

Credentials remain host-side wherever the Pi model gateway works; if the installed SDK cannot support it, report the concrete capability gap and design an equivalent scoped broker. Do not weaken isolation by handing all global credentials to a shell tool. Conversation host tools have no unrestricted shell.
