# Independent orchestrator critique

Critic: `01a0b6bd-3d14-7300-b700-13e1ea8b29ee`, GPT-5.6 Luna high, read-only
review of revision `2ad955e`.

The critic confirmed the live quota route, tests, and non-persistent behavior,
then identified these unresolved findings:

- token-level streaming is not implemented; the current event transport is
  replay/close and the browser refreshes on completion events;
- failed orchestrator turns do not yet persist a bounded terminal failure;
- context selection can include messages newer than the claimed turn;
- Telegram messages do not yet enqueue orchestrator turns;
- workspace mutation routes still need owner authentication;
- browser retries generate a new dedupe key each submit.

The review is recorded as NO-GO for the full product gate. These findings are
not represented as completed functionality.

Re-review of revision `1354619` after service restart found no new critical,
high, or medium findings. It directly confirmed the `sequence <=
user_message.sequence` cutoff, active API/worker units, HTTP 200 live quota
response, and the focused regression suite.
## Latest independent hole audit

- UTC: 2026-09-19T00:05Z; reviewed revision `3a029c7` and the live runtime.
- Actual critic runtime reported itself as GPT-5 Codex despite the requested
  Luna-high override; no Luna identity is claimed for this row.
- Decision: NO-GO, confidence 97/100.
- Verified: live quota invokes `codexctl status` without changing persisted
  quota rows; the real art PNG is persisted with an `art_artifact_id`; API,
  production worker and Telegram services are active; focused API/worker/
  systemd checks pass.
- High findings still open: no owner authentication; SSE is finite replay and
  the browser polls instead of receiving token deltas; orchestrator failures
  can remain indefinitely running; art calls are absent from usage accounting;
  and the production path is still one short model call rather than a durable
  50–150 page section workflow.
- Medium findings: the dashboard does not yet render/download production
  artifacts, Telegram same-conversation delivery is unproven until `/use`
  plus free text is exercised, and the evidence was uncommitted at review time
  (resolved by commit `a433983`). The quota parser's multi-account truncation
  was also repaired in `a433983` with a redacted `account_index` and test.

Earlier findings and repairs remain below.

## 2026-09-19 security and streaming re-review

Critic: `01a0b715-61f3-7352-aedb-edb5d96fd2f8`, actual GPT-5 Codex runtime
(requested Luna high; no Luna identity claimed), read-only review of
`c165d43` and the uncommitted follow-up before `952bfc2`.

Decision: NO-GO. The critic verified active services, HTTPS on non-loopback
listeners, loopback worker compatibility, owner/worker separation, the login
limiter, and focused tests. It found that default self-signed TLS does not
authenticate the server, failure redaction needed broader patterns, OpenAPI
security needed exact AND/header contracts, and in-memory login limits were
per-listener. The code repairs for the latter three are in `952bfc2`; the
self-signed trust limitation remains explicitly open in
`evidence/P10/security-repair.md`.

The same critic reviewed the page/artifact packet through `205d1ca` and found
page bounds, art usage normalization, connection-test OpenAPI detail,
artifact hash verification, and final JSONL flushing gaps. Revisions `c53c700`
and `6cfdb5d` repair those findings with focused tests. The critic's runtime
was GPT-5 Codex despite the requested Luna high override; no Luna identity is
claimed.
