# Live production restart hole and repair

- UTC: 2026-09-19; disposable project `e7174dc2-071a-4d00-be93-1dd16d89b3f7`,
  run `02824531-6360-41d7-9459-7c87f12f89d4`, job
  `49c2bea2-080b-407c-8242-a74b5fce768f`.
- The approved low-cost nonfiction job was claimed by the rootless worker at
  fencing generation 1. The user worker service main process was killed by
  systemd, restarted automatically, and reclaimed the same durable job at
  generation 2 with attempt 2. This proves the lease/reclaim boundary, not a
  completed production acceptance.
- The run included an approved cover direction. The restarted worker reached
  the Codex app-server image subprocess, which exposed that the adapter had no
  bounded timeout and remained running while heartbeats continued. The
  disposable run was cancelled through the fenced private cancel route with
  cancellation epoch 1 before another retry could start.
- Result: H2/H4 remain unpassed. No output from this cancelled run is counted
  as a book or image acceptance. The follow-up repair adds a default 120-second
  timeout, parent abort handling, child termination and redacted bounded errors
  in `apps/worker/src/codex-art.ts`, with seven focused tests passing.
