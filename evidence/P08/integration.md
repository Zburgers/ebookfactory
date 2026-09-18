# P08 artifact-validation evidence

- Code revision: `bd9e6c8`
- UTC: 2026-09-18
- Artifact behavior: relative paths reject traversal and symlink parents; writes enforce a 50 MiB limit, fsync staged bytes, atomically rename into the private artifact root, and persist immutable byte count/SHA-256 metadata
- Document behavior: latest persisted section revisions render deterministically to Markdown in order
- Tests: artifact path traversal/symlink rejection and immutable hash/write behavior pass; full `make verify` passes with 11 ordinary tests and 9 PostgreSQL recovery/API tests
- Limitation: Pandoc, LibreOffice, EPUBCheck and Kindle Previewer were unavailable in P00; no EPUB/PDF/DOCX package, cover, reader review or Kindle evidence is claimed, and publishing/art points remain zero
