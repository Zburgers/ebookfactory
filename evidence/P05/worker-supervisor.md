# P05 durable worker supervisor evidence

- UTC: 2026-09-18T20:28:19Z
- Revision: `0e691d0`
- Scope: `apps/worker/src/supervisor.ts` and `scripts/tests/test_worker_supervisor.sh`
- Critic: `01a0b62b-b9a9-7660-8002-a32caff55276`, GPT-5.6 Luna low, separate read-only review

The trusted worker loop now claims jobs with the requested lease duration,
renews leases during execution, completes jobs with dictionary-shaped result
references, reports retryable execution failures, and keeps polling through
transient claim/mutation transport errors with bounded backoff. Abort signals
propagate through claim, heartbeat, completion and failure HTTP requests.

Real local HTTP behavior checks cover:

- schema-shaped UUID/datetime lease fixtures;
- stale heartbeat `409` cancelling execution and suppressing completion/failure;
- transient completion `503` retry and abort-suppressed retry;
- failure callback connection loss without terminating the supervisor;
- external shutdown without a false failure report;
- cancellation of a delayed in-flight claim request;
- null result normalization to `{}` for the API dictionary contract.

Verification:

```text
make verify
20 passed, 9 skipped, 2 warnings
9 PostgreSQL recovery tests passed
worker supervisor lifecycle/request-cancellation/failure/shutdown checks passed
rootless containment check passed
```

This packet proves the worker lease/callback boundary and restart-safe durable
behavior in isolation. It does not claim H2: no production-through-Podman
worker process was intentionally killed and recovered in this packet, and the
full autonomous production journey still needs that evidence.
