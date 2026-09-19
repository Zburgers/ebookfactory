# Live Codex art evidence

- UTC: 2026-09-18T23:57Z; revisions `25268b1` and `3a029c7`.
- Project `ca2b2f2a-33ce-471a-9f1f-ef547849d861`; run
  `3e011e57-021e-4641-adef-6998a484a1ce`.
- The real rootless production worker completed the run after bounded retries
  exposed and repaired current app-server `saved_path` parsing and
  provider-qualified model normalization.
- The project API returned the generated image artifact
  `3e011e57-021e-4641-adef-6998a484a1ce/exec-584b7b67-eb23-4796-b2bc-633d2d3105b6.png`:
  `image/png`, 1,385,196 bytes, SHA-256
  `51dc6b93c3fe9b3a83d91572b66b1419d9cde9c4bc59da8fef67bcb6b4bdb1f0`.
- The event timeline contains `production.output.accepted` and
  `job.completed`; durable result references include `art_artifact_id`.
- The same run persisted Markdown output and a finalized usage call.

This passes the automated subscription-backed image-output gate. It does not
claim the full 50–150 page staged manuscript workflow, visual Kindle review,
or owner revision of the image.
