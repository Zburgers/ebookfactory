# Live art-backed export evidence

Observed 2026-09-19 UTC on revision `878ba83`, with the rootless API service
active on port 6969 and PostgreSQL migration head `a1b2c3d4e5f6`.

- Project: `ca2b2f2a-33ce-471a-9f1f-ef547849d861`
- Manuscript revision: `09e143bf-10c4-467a-9dd7-fccc72ca24f9`
- Selected persisted image artifact: `53b47184-43ba-462b-8907-812ab49af575`
- Source image: PNG, 1254x1254, 1,385,196 bytes,
  SHA-256 `51dc6b93c3fe9b3a83d91572b66b1419d9cde9c4bc59da8fef67bcb6b4bdb1f0`
- Authenticated `POST /projects/{project}/exports/{revision}` with the exact
  `art_artifact_id` returned `200`, `structurally_validated`, and 10 members.
- Generated cover: JPEG, 1600x2560, 299,165 bytes,
  SHA-256 `a56573b2ded6083f8ffb42d32839a68627f846e9bda74b71abe41847bd351978`.
- `metadata.json` records structured revisioned-manuscript provenance and the
  exact source artifact ID, hash, MIME type, dimensions, layout and final-cover
  hash. Source bytes remained unchanged.
- `scripts/validate-epub.sh` on the live package returned exit 0:
  `0 fatals / 0 errors / 0 warnings / 0 infos`.

The exact-call `artifacts.usage_call_id` binding, retry fencing, legacy metadata
fail-closed behavior and cross-project/alternate-art rejection are covered by
the PostgreSQL/API regression suites. This evidence does not claim owner image
approval, Kindle Previewer certification, or a new provider image invocation;
the persisted source is the real Codex image already recorded in the database.
