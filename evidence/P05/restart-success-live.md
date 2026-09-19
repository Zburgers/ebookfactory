# Successful production recovery evidence

- UTC: 2026-09-19; delivered code revision `c7c7a8c` (worker implementation
  `e3e9185`). Disposable nonfiction project
  `d72a330c-134a-4b66-b91c-263d00ecb84f`, brief
  `f6f485d2-c966-446a-b65a-75b726474b94`, run
  `3e4e6f05-3aba-499d-af8a-438dcfe876d3`, and job
  `675a67a0-b31d-47cc-9fe7-3c0092f5d381`.
- The same exact approval was submitted twice. Both responses returned the
  same run, task and job identifiers; no duplicate production run was created.
- The rootless worker was killed after claiming generation 1. Systemd
  restarted it, the durable lease expired, and the replacement reclaimed the
  same job at generation 2, attempt 2. The job then completed successfully in
  `draft_review`.
- PostgreSQL and API checks agree: six non-empty manuscript sections, a
  7,158-byte Markdown artifact with SHA-256
  `b81dbfb069831ad11bead321375decfad7f45832233d213f46dde327bf39961c`, and
  usage lineage provider `openai-codex`, model
  `openai-codex/gpt-5.6-luna`. The nonfiction owner revision chained revision
  1 to revision 2 without deleting the parent. A separate real fiction run
  `234f6511-212c-40c9-be91-c5e616639c8c` completed five non-empty sections;
  its owner revision also chained revision 1 to revision 2.
- This is stronger recovery evidence than the earlier cancelled art probe, but
  it does not claim a literal browser-close trace or the full autonomous
  outline/research/review task graph. H2/H4 therefore remain conservative in
  the scorecard until those missing behaviors are directly evidenced.
