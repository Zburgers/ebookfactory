# P05 document-core evidence

- Code revision: `c3cbf4c`
- UTC: 2026-09-18
- Real API journey: PostgreSQL tests passed project creation, brief hashing, duplicate approval convergence, section creation, immutable section revisions and stale editor rejection; the test leaves zero uniquely named fixture projects
- Revision behavior: briefs receive deterministic SHA-256 content hashes; section revisions retain parent IDs, source/knowledge references and immutable content hashes; review findings require a revision or artifact reference
- API surface: project/brief/approval, section creation and section-revision endpoints are generated into the checked-in OpenAPI/TypeScript contracts
- Verification: `make verify` passed; ordinary pytest reported 7 pass and 9 DB-test skips without exported env, while the dedicated PostgreSQL recovery target passed 9 tests; rootless sandbox and worker checks also passed
- Limitation: no real fiction/nonfiction generated manuscript, bounded Pi production runner, source/knowledge ingestion, editorial repair, owner draft review, or budget-block behavior is claimed yet
