# Durable owner art-review workflow

Date: 2026-09-19

The delivered review workflow is project-scoped and durable. Image artifacts
carry `owner_review_state`, note, and timestamp in PostgreSQL. The API requires
the caller's expected state and locks the row, so a stale decision returns
`409`. Derived export artifacts cannot be reviewed. A `revision_requested`
source image is excluded from new export selection, export replay fails closed,
and package-member downloads return `409` until a replacement source is used.
Artifact listing, download, review findings, and finding resolution all reject
inconsistent cross-project relationships.

Evidence:

- `uv run --directory apps/api pytest -q tests/test_exports.py tests/test_quota.py`
  returned 19 passed.
- `scripts/tests/test_contract_generation.sh` passed after regenerating the
  checked-in OpenAPI and TypeScript contracts.
- `node --check apps/web/src/app.js` and the web verify command passed.
- Independent Luna-high audit found the above access-control and stale-download
  holes; the repairs are commits `d6a1f9f` and `ca220f0`, followed by the UI
  label correction `79fb80e`.

This proves the workflow implementation, not an owner decision. Actual owner
approval/revision of a live image remains an operational gate until the owner
uses the dashboard controls.
