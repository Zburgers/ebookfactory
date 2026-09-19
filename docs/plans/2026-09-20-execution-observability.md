# Execution Observability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `shipyard:shipyard-executing-plans` to execute this plan task by task with verification checkpoints.

**Goal:** Turn the current state-heavy dashboard into a thoughtful, functional ebook factory: guide the owner through the complete journey from idea to package, show useful book metadata in a dedicated place, support flexible genres and page/word targets, make every production decision and agent operation observable, and safely re-enter production when a revision is requested.

**Architecture:** PostgreSQL remains the source of truth. Existing `events`, `messages`, `production_runs`, `tasks`, `attempts`, `jobs`, `artifacts`, and `usage_calls` are extended with append-only lifecycle events and one bounded owner-only execution aggregate. The dashboard is reorganized into a clear library → book workspace → production journey: a compact overview carries title/profile/brief metadata, a guided brief editor owns all book setup, a control room shows the real execution trace, and manuscript/artifact/review/package work is grouped by purpose. This is operational transparency, not hidden chain-of-thought: show prompts/context that are safe and bounded, model/provider/tool calls, concise result summaries, decisions, errors, and artifact/usage references; never expose private internal reasoning or credentials.

**Tech Stack:** FastAPI + SQLAlchemy/PostgreSQL, existing durable event/outbox helpers, TypeScript worker supervisor and Pi/Codex adapters, vanilla web dashboard with the existing CSS/view-model layer, pytest and the current `make verify` checks.

---

## Current evidence and root cause

The live project `Integrated art smoke` (`ca2b2f2a-33ce-471a-9f1f-ef547849d861`) has zero `messages`. Its durable event stream contains `run.approved`, three `job.claimed` retries, `production.output.accepted`, and `job.completed`, but no owner-review event. Its task table contains one historical production task and its image is `revision_requested` with the note `Its too simple i want some more anime type of illustrations particular to the theme`.

The current behavior is therefore:

1. Brief approval creates outline, production, and review tasks/jobs directly. It does not create a model chat turn.
2. Direct dashboard/Telegram messages create `messages` and an `OrchestratorTurn`; production tasks do not write their operational summaries back into that conversation.
3. `Request revision` only updates the immutable artifact's owner-review fields. It does not append an event, enqueue a job, change the run, or invoke an agent.
4. The image path is Pi manuscript production followed by the bounded Codex app-server image adapter when `brief.art_direction` exists. The API persists the returned image and usage provenance, but the dashboard does not show that causal path.
5. The event timeline intentionally drops orchestrator deltas and renders most payloads as coarse labels, so even existing durable work is not inspectable.

The implementation will make these facts visible immediately, add the missing durable events, and make a revision request a fenced, deduplicated artwork-revision job rather than silently leaving the project blocked. The UI will state when no agent was eligible or when a provider call was blocked, so it never implies work happened when it did not.

## Product audit findings from the current screens

- The studio currently presents two large cards (`Shape the idea` and `Make it exact`) before the owner knows which book is selected or what its current brief says. This makes a finished run look like an empty project and creates a false sense that chat is the primary production surface.
- Metadata exists in exported JSON/CSV files but has no first-class home in the workspace. The owner should be able to inspect and edit the book identity, audience, language, genre, length target, formats, art direction, and revision hash without downloading a package.
- The setup form hard-codes only Fiction/Nonfiction at project creation and uses a cramped side panel with pages/words hidden behind a select. A versatile factory needs a free-form genre/category plus useful presets and one clear length control with validation.
- The seven-card stage rail, repeated numbered eyebrow headings, and full-width artifact links compete for attention. The page needs one journey timeline with a current focus and collapsible detail, not many unrelated “panels.”
- The current artifact grid is denser than the information it conveys and mixes metadata files, manuscript formats, images, and exports. Grouping by `Book package`, `Manuscript`, `Artwork`, and `Metadata` will make actions discoverable.
- The current project state is a snapshot. The owner needs a journey view where past stages remain visible as completed work, current work is actionable, and future work is understandable even before it starts.
- The current interface assumes a dashboard owner token, but the live browser cannot be audited without that credential. Static checks and owner-authenticated API tests must cover the redesign; live visual verification will be recorded as pending until the owner supplies the token.

## Safety and product boundary

- Keep all execution details owner-authenticated and project-scoped. Do not make artifacts, event payloads, prompts, model calls, or usage data public.
- Do not render raw worker lease data, capability tokens, API keys, environment values, or unbounded provider output.
- Do not fabricate assistant messages. A system-generated lifecycle update is labelled `Orchestrator update`; a model response remains an actual assistant message.
- Do not expose hidden chain-of-thought. The visible record is a concise operational trace: action, intent/context, result, decision, error, and references.
- Preserve existing event kinds and API behavior where possible; additive events are preferred so replay and old clients remain valid.
- A revision job must create a new immutable image artifact and retain the superseded artifact and its review history. Its input includes the original art direction plus the owner note, and its dedupe key binds the source artifact/hash and note hash.
- Automatic revision generation can consume provider/subscription usage. The UI must explain this before submission and the API must expose the resulting usage call/unknown fields honestly. No Amazon upload, purchase, or external publication is added.

## Work packets

### Packet 0 — Product audit and information architecture

**Files:** `docs/UX-AUDIT.md`, `apps/web/index.html`, existing `apps/web/src/view-models.js` tests.

Document the real owner journey and the screen hierarchy before adding controls. Use the existing screenshots and a read-only inventory of routes, models, and current UI behavior. Define the primary actions for each phase: shape, specify, approve, produce, review, revise, package, preview. Establish the content rules for metadata, stage labels, artifact groups, and empty/error states. The audit must explicitly identify dead controls, duplicate labels, hard-coded genres, hidden targets, unobservable work, and any action that consumes provider usage.

Acceptance: a short UX audit maps each visible control to a real API operation or marks it for removal; no new UI element is added without a corresponding purpose and state.

### Packet 1 — Durable lifecycle and owner-review semantics

**Files:** `apps/api/app/jobs.py`, `apps/api/app/main.py`, `apps/api/app/reviews.py`, `apps/api/app/events.py`, `apps/api/app/models.py` only if a field is proven necessary, `apps/api/tests/test_jobs.py`, `apps/api/tests/test_exports.py`, `apps/api/tests/test_reviews.py`.

**Red:** Add tests that assert approval emits a plan/task-enqueued record, job claims/completions expose task/provider/attempt context, and an owner art review emits `artifact.owner_reviewed` with decision/note and does not leak cross-project data. Add a failing behavior test for revision request: one deduplicated revision job is created, the source artifact remains immutable, the run enters a visible revision state, and a stale expected review state is rejected.

**Green:**

- Emit a bounded `run.plan.created` or additive `task.enqueued` event for every task/job with parent/dependency IDs, task type, input revision IDs, and dedupe key (not secrets).
- Emit an `agent.started`/`agent.completed` lifecycle event alongside existing job events, including attempt number, generation, provider/model, timing, status, result refs, and bounded error class.
- Append `artifact.owner_reviewed` for every accepted owner decision, including artifact ID/hash, prior/new state, decision, bounded note, reviewed timestamp, and `revision_job_id` when one is enqueued.
- Add review finding create/resolve events so replay explains editorial decisions too.
- Implement an idempotent artwork revision enqueue path using the existing durable task/job tables and fencing model. It must bind to the source artifact/run and create a new revision task/job with the owner note in a bounded task input/result reference, never overwrite the source file, and avoid enqueueing a second job for the same artifact + note hash.
- Route the worker through the existing Codex art adapter with a bounded prompt composed from art direction plus owner feedback; persist a new image artifact and usage provenance through the existing production-result boundary. Add explicit failure/checkpoint events.

**Focused verification:** API tests for event payloads, idempotence, stale review concurrency, source-artifact immutability, project scoping, and the worker request contract. Run the relevant pytest files before moving on.

### Packet 2 — Owner-only execution aggregate API

**Files:** `apps/api/app/main.py`, a small `apps/api/app/execution.py` helper if it keeps query/serialization code cohesive, `apps/api/tests/test_execution.py`.

**Red:** Add endpoint tests for unauthorized access, project scoping, bounded response size, stable ordering, a project with no messages, a project with direct orchestrator messages, a production run with retries, owner review, tasks/attempts/jobs, artifacts, and usage calls.

**Green:** Add `GET /projects/{project_id}/execution` returning a bounded aggregate:

- project/run summary and current state;
- actual conversation messages and orchestrator-turn state/provider/model;
- task tree with parent/dependency/input revision IDs, task/job/attempt statuses, worker generation, timing, provider/model/session identifiers where safe, concise result refs, and error summaries;
- artifact provenance, including image generation provider/model/call/usage linkage and owner-review history;
- normalized usage calls with reported/estimated/unknown fields;
- ordered replay activities with safe payload projection, including grouped/condensed deltas and owner-review decisions.

Use server-side limits and allow an `after_event_id`/`limit` cursor for incremental reloads. Verify project ownership through the same relationship checks as artifact/export routes. Do not return arbitrary JSON blobs or worker credentials.

**Focused verification:** API tests exercise real SQLAlchemy serialization, project isolation, limit enforcement, replay cursor behavior, and absence of sensitive fields. Run API tests and `make verify`'s web/API portions.

### Packet 3 — Control-room dashboard and replay

**Files:** `apps/web/index.html`, `apps/web/src/app.js`, `apps/web/src/view-models.js`, `apps/web/src/styles.css`, `apps/web/tests/view-models.test.mjs`, any existing web test harness files.

**Red:** Add view-model tests for task-tree grouping, lifecycle labels, review/agent event summaries, grouped orchestrator deltas, empty-chat explanation, and image provenance rendering.

**Green:** Add an owner-visible `Orchestrator control room` section that includes:

- a truthful empty state when no direct owner/model chat exists: `No owner chat turn was used for this production run; production was approved directly and is shown below`;
- the actual conversation transcript, with owner, assistant, Telegram, and clearly labelled system/orchestrator updates separated;
- a nested run → task → attempt tree showing queued/running/succeeded/retry/failed/blocked state, dependencies, inputs, provider/model, duration, retry generation, and output links;
- a causal activity feed that preserves run approval, task enqueue/start/checkpoint/complete, provider/image call, artifact creation, review submission, revision enqueue, and errors; deltas are grouped into expandable bounded transcript entries rather than silently discarded;
- review entries in replay with the owner note and the exact artifact/revision they changed;
- an image provenance card explaining `Codex app-server → worker → immutable artifact`, model/provider/call/usage status, art-direction/feedback summary, dimensions/bytes/hash, and whether a revision agent is queued/running/complete;
- explicit statuses for `recorded only`, `queued`, `running`, `blocked`, and `completed` so the owner can tell what happened after a button press.

Keep all user/provider data inserted through text nodes or escaped render helpers. Refresh the aggregate after messages, approvals, review decisions, SSE events, and reconnects. Preserve existing artifact tile/download improvements.

**Focused verification:** run web unit tests, build/static checks, and inspect the rendered dashboard with the existing preview/browser route if available. Verify refresh and closed-tab/reconnect behavior against durable state.

### Packet 3b — Ebook workspace information architecture and visual cleanup

**Files:** `apps/web/index.html`, `apps/web/src/app.js`, `apps/web/src/view-models.js`, `apps/web/src/styles.css`, web tests.

Refactor the Studio into a deliberate workspace rather than adding more cards:

- Add a compact `Book overview` block with title, profile/genre, language, audience, target length, output formats, current revision hash, and a link to the full metadata editor.
- Replace the long repeated headings and decorative indexes with a small number of meaningful zones: `Overview`, `Journey`, `Control room`, `Manuscript`, `Artwork`, `Package`, and `Metadata`.
- Make the journey a horizontal/vertical phase map that shows completed evidence, the current owner action, and the next expected gate. Keep prior phases inspectable.
- Move metadata into a dedicated editable drawer/panel with controlled fields: title, subtitle, author/pen name, description, language, genre/category, audience, length mode, min/max pages or words, output formats, cover/art direction, and keywords. Preserve unknown/unset values as `Not set`; never invent metadata.
- Replace the genre dropdown with a searchable/free-form category input plus a few non-exclusive suggestions (fiction, nonfiction, memoir, guide, workbook, poetry, children’s, business, technical, other). Project creation should not limit the factory to two profiles; profile remains a production behavior choice while genre is user metadata.
- Replace the awkward length side panel with a clear segmented `Pages`/`Words` choice, paired minimum/maximum inputs, inline range validation, and a short explanation of how page estimates work. Keep the active mode visible after reload.
- Group artifacts into purposeful shelves with one-line explanations and action priority. Keep download/preview/review buttons, but move hashes, MIME, paths, and provenance under `File details`.
- Make empty states useful: tell the owner how to create the next real thing, why the chat is empty, what is currently running, and which action can unblock the journey.
- Use the control-room aggregate to populate the overview and journey; do not derive a false “complete” state from a single project string.

**Focused verification:** browser snapshot at desktop and narrow viewport where possible; test keyboard labels, no horizontal overflow, free-form genre persistence, pages/words validation, metadata refresh, and artifact shelf grouping. Remove labels/cards that do not map to user decisions.

### Packet 4 — Documentation, usage/Kindle/art decision surface, and manual journey QA

**Files:** `docs/DESIGN.md`, `docs/CONTRACTS.md`, `docs/INTEGRATIONS.md`, `docs/PUBLISHING.md`, `docs/STATUS.md`, `docs/SCORECARD.md`, `docs/RUNBOOK.md`, `docs/AGENT_LEDGER.md`, `evidence/` only for non-sensitive reproducible evidence.

Document the exact owner journey:

1. shape idea or approve brief;
2. plan and enqueue durable tasks;
3. outline/manuscript/review/art calls;
4. inspect artifacts and provenance;
5. submit a revision or approval;
6. observe the new immutable revision and usage;
7. validate/export and perform Kindle preview when available.

Run a fresh synthetic short-book journey (one fiction or nonfiction fixture) from the dashboard/API, then manually inspect the event/task/artifact/usage chain and download/open Markdown, DOCX, PDF, and EPUB. Record holes and remediate code/docs where possible. Keep Kindle preview, live owner-art visual approval, and provider billing/quota limitations explicit rather than marking them complete without evidence.

The final report will separate:

- actual provider usage versus estimates and unavailable billing/quota fields;
- Kindle Previewer availability and the best next step (local Kindle Previewer/Kindle Create if installed, otherwise owner-run visual check with exact command and evidence to return);
- live owner art review (what can be automated and what still requires the owner’s visual judgment);
- any missing owner credential/decision that cannot be safely inferred.

## Execution order and commits

1. Commit this plan.
2. Execute Packet 1 with red/green tests and commit `feat(api): persist execution lifecycle and revision decisions`.
3. Execute Packet 2 and commit `feat(api): expose owner execution trace`.
4. Execute Packet 3 and commit `feat(web): add orchestrator control room`.
5. Execute Packet 3b and commit `feat(web): shape the book workspace journey`.
6. Execute Packet 4, run full verification and manual QA, append status/scorecard/ledger evidence, and commit `docs: record execution observability acceptance`.
7. Push the branch `codex/ebook-factory-v2` and verify the deployed service on `192.168.29.14:6969` after a controlled restart. Do not claim live success until `/ready`, the execution endpoint, review event path, artifact download, metadata flow, and the UI route are each checked.

If a provider credential or external preview tool is unavailable, finish all independent code and evidence work, mark that gate `PARTIAL`/`BLOCKED`, and consult the owner only with the exact missing input or decision.
