# Delivery scorecard

Current score: **89/100 — durable runtime/containment, real production with
reviewed revision lineage, live usage attribution, dashboard document flow,
structural publishing packages and the live Telegram owner loop are evidenced;
external publishing/quota and owner-art-review gates remain.**

The latest implementation adds live orchestrator delta relay, owner-boundary
repairs, live non-persistent quota reads, a corrected page-target prompt, and a
durable outline-to-production-to-review run with real Luna usage lineage. By
explicit local-network owner choice, the private-LAN listener is plain HTTP and
the Tailscale listener remains HTTPS. A default generated Tailscale certificate
still lacks authenticated server identity; that remains a separate
transport-trust finding from the H1 provider-call gate.

The reviewed export packet now binds image artifacts to their exact usage call
and attempt, verifies canonical package members, and fails closed on legacy
placeholder provenance. A live persisted Codex image produced a 10-member
package that passed EPUBCheck (`evidence/P08/art-export-live.md`).

The owner art-review workflow is now durable, project-scoped and fail-closed
for stale source images and derived packages (`evidence/P08/art-review-workflow.md`).
The score remains conservative at 89 because no live owner review decision has
been performed yet.

The outline-stage packet now adds a durable dependency-gated outline handoff,
terminal dependency failure propagation, typed worker context contracts and
separate outline/manuscript lineage. A real systemd run is recorded at
`evidence/P05/outline-stage-live.md`; the score remains 89 because the real
50-page sectioned replay is now evidenced, but external
publishing/quota gates remain open.

The reconciliation replay also verified the complete multi-section export
scope and owner-revision replacement path in an isolated API journey. This
repairs a packaging correctness hole but does not add Kindle visual-preview or
live owner-decision evidence, so the conservative score remains unchanged.

Revision `25268b1` plus `3a029c7` now prove a real bounded Codex image output
and dashboard-visible production artifact. Revision `2ad955e` proves a real
durable dashboard-to-Luna completion and live
non-persistent quota reads, but it does not close the independent critique's
streaming, failure-recovery, Telegram, authentication, or concurrency findings.

| Area | Earned / available | Evidence |
|---|---:|---|
| Pi/providers | 7/10 | Real dashboard-linked Luna-low subscription call with provider/model/usage attribution and the live Pi catalog/model configuration are evidenced; custom local URL/key protocol integration remains limited to its real local boundary check (`evidence/P06/orchestrator-live.md`, `evidence/P07/live-usage.md`, `evidence/P03/provider-connection.md`) |
| Durable runtime | 14/14 | `evidence/P02/integration.md`; real PostgreSQL recovery suite covers atomic enqueue/dedupe, restart/checkpoint recovery, fencing, cancellation and concurrent claims |
| Containment | 10/10 | Filesystem/secret isolation, enforced network/resource limits and label-scoped reconciliation all pass P04 evidence, including unrelated-container preservation |
| Production | 16/16 | Real fiction/nonfiction output, durable outline-to-manuscript task lineage, fenced context/task lineage, owner revision, resolved review finding and a live pre-publication budget rejection are evidenced (`evidence/P05/real-production.md`, `evidence/P05/outline-stage-live.md`, `evidence/P05/budget-blocking.md`, `evidence/P05/budget-live.md`, `evidence/P06/dashboard-correction.md`) |
| Dashboard | 10/10 | Real Chromium journey covered chat/brief/review, replayed events, section editing, ten export/download links, quota/settings visibility and accessibility checks (`evidence/P06/dashboard-browser-trace.md`) |
| Usage | 8/12 | Real finalized production attribution, exact revision/attempt/artifact-to-call binding, separate Codex-art accounting, idempotent totals, live redacted Codex subscription windows, explicit stale/unknown states and project-scoped call drill-down are evidenced; estimates and Copilot quota remain pending (`evidence/P07/live-usage.md`, `evidence/P07/quota-live.md`, `evidence/P07/quota-live-recheck.md`, `evidence/P07/usage-drilldown.md`, `evidence/P08/art-export-live.md`) |
| Publishing | 10/12 | Real EPUB/PDF/DOCX/Markdown package, cover, metadata, manifests and pinned EPUBCheck validation are evidenced; Kindle preview remains pending (`evidence/P08/publishing.md`) |
| Art | 3/5 | Real subscription-backed image output is persisted and dashboard-visible; owner image revision/layout review remains open (`evidence/P08/art-live.md`) |
| Telegram | 5/5 | Real owner message/assistant response delivery, one-chat/all-project linking, durable active selection, inline `/help` switching, replay safety and allowlist behavior are evidenced (`evidence/P09/telegram-project-switching-live.md`) |
| Operations | 6/6 | Peer-authenticated backup, real isolated PostgreSQL restore with collision-safe temporary cluster, runbook and owned API lifecycle are evidenced (`evidence/P10/isolated-restore.md`, `evidence/P10/`) |

Hard gates: H1 PASS at the API/integration boundary from
`evidence/P06/orchestrator-live.md`; H3 PASS from
`evidence/P04/reconciliation-correction.md`; H8 PASS from
`evidence/P08/art-live.md`; H9 PASS from
`evidence/P10/isolated-restore.md`; H2 PASS is evidenced by
`evidence/P05/browser-close-restart-live.md`. H4 PASS is now supported by the
real 50-page sectioned replay at `evidence/P05/long-book-live.md`, the prior
fiction/nonfiction runs and owner-revision evidence. H6 remains NOT RUN;
H7 PASS is supported by the real package plus EPUBCheck evidence at
`evidence/P08/publishing.md`, with Kindle preview explicitly pending.
H5 PASS is now supported by the real owner Telegram message/response and the
durable project-scoped routing evidence at `evidence/P09/telegram-project-switching-live.md`.
Streaming relay evidence is in
`evidence/P06/streaming-live.md`, while the latest security review remains
NO-GO because default self-signed TLS can be bypassed by a client. Independent Luna critics are now available
for the latest packets; earlier lead critiques remain recorded at `evidence/P00/critique.md`,
`evidence/P01/critique.md`, `evidence/P02/critique.md`,
`evidence/P03/critique.md`, `evidence/P04/critique.md`,
`evidence/P05/critique.md`, `evidence/P06/critique.md` and
`evidence/P07/critique.md`, `evidence/P08/critique.md` and
`evidence/P05/production-seam-critique.md`, `evidence/P08/art-export-live.md`
and `evidence/P10/backup-critique.md`.
Final evidence/revision: integrated slice `e15ceb1` (with Telegram at `ba181f7`);
application delivery remains partial because the listed external hard gates are
not fabricated as passed. Latest worker revision: `0e691d0`; latest provider/service revision: `ca7d6bc`; latest restore revision: `5f9c918`.
