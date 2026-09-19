# Manual ebook journey QA

- UTC: 2026-09-19T14:34:43Z
- Candidate baseline: `bf8230bc9463af5740a123ed1f61d62f20e4f730`
- Repaired revision: `aa31599`
- Scope: isolated SQLite database and temporary artifact root; no live
  PostgreSQL rows, provider account, Telegram account, or publishing account
  was used.
- Boundary: FastAPI `TestClient` plus the real worker claim/context/result and
  export endpoints.

## Journey exercised

1. Create a fiction project and immutable brief.
2. Approve the exact brief hash and enqueue the durable run.
3. Claim the outline and submit an eight-section outline.
4. Claim and submit all eight section-draft tasks.
5. Claim production and submit the server-side assembly sentinel.
6. Claim and complete the review task.
7. Export Markdown, EPUB, PDF, DOCX, cover, metadata, sources, manifest and
   validation members; download representative members through the API.
8. Create an owner section revision and export again, preserving the other
   seven frozen section revisions.

## Findings and remediation

- The first replay exposed a SQLite lease comparison failure: SQLite returned a
  naïve `lease_until`, while production acceptance compared it with aware UTC.
  A regression test now covers the API boundary and the comparison normalizes
  naïve persisted values to UTC.
- The first successful replay exposed an export completeness failure: a
  multi-section run exported only the first section because the API accepted a
  single section revision as its package scope. Export resolution now follows
  the completed production task's dependency-fenced section revisions, records
  all source revision IDs, and substitutes a descendant owner revision for its
  section only. A regression test covers the complete scope.

## Final replay result

- Eight section drafts completed.
- Eight sections appeared in the document view.
- Review completed before export.
- Export package state: `structurally_validated`.
- Package metadata recorded eight source revision IDs.
- Markdown contained all eight section headings and all eight section bodies.
- API downloads for `book.md`, `metadata.json`, and `book.epub` returned 200.
- Owner-revised replay retained all eight sections and contained the corrected
  section body.

This evidence is structural and isolated. It does not close Kindle visual
preview, live owner art approval, provider billing, or unsupported Copilot
quota gates.
