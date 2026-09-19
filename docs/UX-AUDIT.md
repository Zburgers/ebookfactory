# Ebook Factory UX audit

Date: 2026-09-20  
Scope: `apps/web/index.html`, `apps/web/src/app.js`, `apps/web/src/view-models.js`, current owner screenshots, and the durable API contracts.

## Core finding

The application has a useful durable backend, but the dashboard currently presents the backend as a collection of state panels. A book is not a state; it is a journey with decisions, evidence, and outputs. The interface must answer three questions at every point:

1. What book am I working on?
2. What has happened, what is happening, and what can I do next?
3. Where is the source of truth for the book’s metadata, manuscript, artwork, and package?

## Current control audit

| Current surface | Real operation | Problem | Decision |
| --- | --- | --- | --- |
| Project card | `GET /projects`, `POST /projects` | Profile is limited to Fiction/Nonfiction; genre and book identity are absent | Keep profile as production behavior, add free-form genre and a proper book overview |
| Shape the idea | `POST /projects/{id}/messages` | Direct chat is empty for brief-approved runs and looks like the production engine | Keep for owner/orchestrator conversation, explain when a run was approved without chat |
| Make it exact | `POST /projects/{id}/briefs`, approval route | Pages/words are hidden behind a dense side form; art direction is hard-coded | Make brief metadata a first-class editable area with explicit length mode and output selection |
| Seven-card stage rail | Derived from project state/sections/events | Shows a snapshot, not causal history; repeats the same status vocabulary | Replace with one journey map backed by execution evidence |
| What changed | `GET /projects/{id}/events` | Coarse labels omit payload, reviews, task tree, and deltas | Replace/augment with the control room and replay details |
| Draft manuscript | `GET /sections`, `POST /sections/{id}/revisions` | Source is visible, but review/package relationship is unclear | Keep source editing; place it under Manuscript with revision lineage |
| Production artifacts | `GET /artifacts`, protected download | Metadata, package files, and art are one dense shelf | Group by purpose; details and hashes belong behind disclosure |
| Artifact review | `POST /artifacts/{id}/review` | Previously record-only; no event or visible next action | Persist the decision, show it in replay, and enqueue a fenced art revision on request |
| Usage | `GET /usage`, `GET /usage/calls`, quota route | Correctly honest but disconnected from the task/art that consumed it | Link usage calls to control-room tasks and image provenance |
| Settings | provider/catalog/Telegram routes | Functional but separate from book decisions | Leave operational settings separate; show selected model in execution metadata |

## Owner journey

### 1. Shape

The owner creates a project or starts a conversation. The UI records the idea and keeps the active book obvious.

### 2. Specify

The owner fills in book metadata: working title, subtitle, author/pen name, description, profile, genre/category, language, audience, length target, formats, keywords, and art direction. Missing values remain visibly unset. The form validates ranges and explains page estimates.

### 3. Approve

The owner reviews the exact brief revision/hash and approves it. The UI explains that approval creates a durable production run and shows the initial task plan before any work starts.

### 4. Produce

The journey shows outline, section drafting, manuscript assembly/review, and artwork as durable tasks. Each task has a status, model/provider, attempt history, usage link, and result reference. A direct approval may have no chat turn; that is displayed honestly.

### 5. Review

The owner reads the manuscript and sees artifact previews. A review decision is tied to the exact immutable artifact/revision, appears in replay, and either advances the gate or queues a new bounded revision task.

### 6. Revise

Revision creates new immutable output and retains the superseded output. The owner sees the feedback that caused the revision and the new agent attempt. A provider failure or unavailable quota is a visible blocked state, not a fake completion.

### 7. Package and preview

The owner sees a purposeful package shelf (EPUB, PDF, DOCX, Markdown, cover, metadata) and can download protected files. Kindle preview remains a separate external visual gate until an actual preview tool/evidence is available.

## Content hierarchy for the redesign

The Studio should contain these meaningful zones, in this order:

1. **Book overview:** identity and current action.
2. **Journey:** completed evidence, current gate, next action.
3. **Control room:** actual conversation, delegated tasks, replay, usage/provenance.
4. **Manuscript:** source revisions and owner editing.
5. **Artwork:** previews, provenance, owner review/revision.
6. **Package:** validated output formats and downloads.
7. **Metadata:** dedicated edit surface and revision hash.

Decorative labels such as numbered panel indexes and repeated “state/boundary/revision/evidence” strips are not user decisions and should be removed or collapsed into details.

## Guardrails

- No UI control without a real API operation or an explicit disabled/coming-gate explanation.
- No “complete” label based only on a project state when task/artifact evidence says otherwise.
- No raw hidden model reasoning. The owner sees operational summaries, user-facing model output, tool/image calls, decisions, errors, and references.
- No provider call is triggered silently. A revision action states that it queues new work and may consume usage.
- No metadata is inferred or overwritten when it is unavailable; show `Not set`.
- All project data and downloads remain owner-authenticated and project-scoped.

