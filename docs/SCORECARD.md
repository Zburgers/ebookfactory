# Delivery scorecard

Current score: **82/100 — durable runtime/containment, real production with
reviewed revision lineage, live usage attribution, dashboard document flow and
structural publishing packages are evidenced; external hard gates remain.**

The latest implementation adds live orchestrator delta relay and owner-boundary
repairs, but the score is unchanged until the corresponding hard-gate evidence
is complete. In particular, the default generated TLS certificate is encrypted
transport without authenticated server identity; H1 is not marked passed.

Revision `25268b1` plus `3a029c7` now prove a real bounded Codex image output
and dashboard-visible production artifact. Revision `2ad955e` proves a real
durable dashboard-to-Luna completion and live
non-persistent quota reads, but it does not close the independent critique's
streaming, failure-recovery, Telegram, authentication, or concurrency findings.

| Area | Earned / available | Evidence |
|---|---:|---|
| Pi/providers | 4/10 | Real Luna-low subscription call with provider/model/usage attribution and a custom local URL/key connection-test boundary are evidenced; a real dashboard-configured Pi answer and browser acceptance remain pending (`evidence/P07/live-usage.md`, `evidence/P03/provider-connection.md`) |
| Durable runtime | 14/14 | `evidence/P02/integration.md`; real PostgreSQL recovery suite covers atomic enqueue/dedupe, restart/checkpoint recovery, fencing, cancellation and concurrent claims |
| Containment | 10/10 | Filesystem/secret isolation, enforced network/resource limits and label-scoped reconciliation all pass P04 evidence, including unrelated-container preservation |
| Production | 16/16 | Real fiction/nonfiction output, fenced context/task lineage, owner revision, resolved review finding and a live pre-publication budget rejection are evidenced (`evidence/P05/real-production.md`, `evidence/P05/budget-blocking.md`, `evidence/P05/budget-live.md`, `evidence/P06/dashboard-correction.md`) |
| Dashboard | 10/10 | Real Chromium journey covered chat/brief/review, replayed events, section editing, ten export/download links, quota/settings visibility and accessibility checks (`evidence/P06/dashboard-browser-trace.md`) |
| Usage | 8/12 | Real finalized production attribution, separate Codex-art call accounting is implemented and tested but not yet proven by a new live image call, plus idempotent totals, live redacted Codex subscription windows, explicit stale/unknown states and project-scoped call drill-down are evidenced; estimates and Copilot quota remain pending (`evidence/P07/live-usage.md`, `evidence/P07/quota-live.md`, `evidence/P07/usage-drilldown.md`) |
| Publishing | 10/12 | Real structurally checked EPUB/PDF/DOCX/Markdown, cover, metadata and manifests are persisted; EPUBCheck and Kindle preview remain pending (`evidence/P08/publishing.md`) |
| Art | 3/5 | Real subscription-backed image output is persisted and dashboard-visible; owner image revision/layout review remains open (`evidence/P08/art-live.md`) |
| Telegram | 1/5 | Real `/help` receipt and outbox delivery are evidenced; same-project free-text loop and real sender rejection remain open (`evidence/P09/telegram.md`) |
| Operations | 6/6 | Peer-authenticated backup, real isolated PostgreSQL restore with collision-safe temporary cluster, runbook and owned API lifecycle are evidenced (`evidence/P10/isolated-restore.md`, `evidence/P10/`) |

Hard gates: H3 PASS from `evidence/P04/reconciliation-correction.md`; H8 PASS
from `evidence/P08/art-live.md`; H9 PASS from
`evidence/P10/isolated-restore.md`; H1, H2, H4–H7 remain NOT RUN. H4 now has real output and owner-review evidence but
still needs a restart-through-production proof; the worker lease boundary is
now directly tested in `evidence/P05/worker-supervisor.md`, but that is not a
full H2 production restart proof. Streaming relay evidence is in
`evidence/P06/streaming-live.md`, while the latest security review remains
NO-GO because default self-signed TLS can be bypassed by a client. Independent Luna critics are now available
for the latest packets; earlier lead critiques remain recorded at `evidence/P00/critique.md`,
`evidence/P01/critique.md`, `evidence/P02/critique.md`,
`evidence/P03/critique.md`, `evidence/P04/critique.md`,
`evidence/P05/critique.md`, `evidence/P06/critique.md` and
`evidence/P07/critique.md`, `evidence/P08/critique.md` and
`evidence/P05/production-seam-critique.md` and `evidence/P10/backup-critique.md`.
Final evidence/revision: integrated slice `e15ceb1` (with Telegram at `ba181f7`);
application delivery remains partial because the listed external hard gates are
not fabricated as passed. Latest worker revision: `0e691d0`; latest provider/service revision: `ca7d6bc`; latest restore revision: `5f9c918`.
