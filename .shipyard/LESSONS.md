# Shipyard Lessons Learned

## [2026-09-20] Phase: Usage, billing, and live orchestrator reconciliation

### What Went Well
- Running a real owner turn after the worker repair proved that durable chat, tool calls, gate updates, child enqueueing, and child completion can be observed together rather than inferred from unit tests.

### Surprises / Discoveries
- A valid GitHub PAT can authenticate the GitHub identity endpoint while the personal Copilot billing endpoint still returns 404 when billing is absent or managed elsewhere; the UI must expose that distinction.

### Pitfalls to Avoid
- Do not scope the Usage page silently to the selected book when the owner is asking for account-wide totals; show workspace totals and project drill-down as separate scopes.
- Do not assume a new durable task type will take an existing worker result route; the route decision must have a regression test for every allowlisted task type.

### Process Improvements
- Every live provider audit should test identity, billing scope, response status, and UI wording separately, while every new orchestrator/child task type should get one real end-to-end route probe.

---

## [2026-09-20] Phase: Kindle preview evidence and orchestrator skill integration

### What Went Well
- A preview result can be made durable without weakening package immutability by recording the exact EPUB hash, preview surface, tool version, and owner result as an event.
- Explicit Pi skill paths preserve worker isolation while still giving the main orchestrator reusable KDP workflow guidance.

### Surprises / Discoveries
- A structurally valid EPUB and EPUBCheck pass do not prove Kindle visual acceptance; the owner must inspect a rendered preview on an actual Kindle preview surface.
- The requested `kdp-publish` skill references sibling `kdp-audit` and `kdp-listing` skills, so installing only the named skill leaves the orchestrator workflow incomplete.

### Pitfalls to Avoid
- Do not let a KDP skill trigger uploads, purchases, account changes, pricing decisions, KDP Select enrollment, or publication; those actions require an explicit owner decision and an authenticated external surface.
- Do not load third-party skills into production child workers; keep `--no-skills` and pass trusted skills only to the main orchestrator.

### Process Improvements
- Treat every external acceptance gate as a first-class, hash-bound checkpoint in the product, with a visible replay event and an explicit distinction between owner evidence and platform acceptance.
- Reconcile installed workflow skills against their referenced sibling skills and pin each source revision before wiring them into a service.

---
