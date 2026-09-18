# Delivery scorecard

Current score: **65/100 — durable runtime/containment, real production with
reviewed revision lineage, live usage attribution, dashboard document flow and
structural publishing packages are evidenced; external hard gates remain.**

| Area | Earned / available | Evidence |
|---|---:|---|
| Pi/providers | 4/10 | Real Luna-low subscription call with provider/model/usage attribution; custom URL/key protocol integration and a browser-driven provider connection check remain pending (`evidence/P07/live-usage.md`) |
| Durable runtime | 14/14 | `evidence/P02/integration.md`; real PostgreSQL recovery suite covers atomic enqueue/dedupe, restart/checkpoint recovery, fencing, cancellation and concurrent claims |
| Containment | 10/10 | Filesystem/secret isolation, enforced network/resource limits and label-scoped reconciliation all pass P04 evidence, including unrelated-container preservation |
| Production | 14/16 | Real fiction/nonfiction output, fenced context/task lineage, owner revision and a resolved review finding are evidenced; measured budget blocking remains pending (`evidence/P05/real-production.md`, `evidence/P06/dashboard-correction.md`) |
| Dashboard | 7/10 | Chat/brief/review, event monitoring, section editing and export downloads are implemented and smoke-tested; a full interactive Chromium trace and richer task tree remain pending (`evidence/P06/dashboard-correction.md`) |
| Usage | 4/12 | Real finalized call attribution and idempotent totals are evidenced; estimates, corrections, Codex/Copilot quota snapshots and drill-down remain pending (`evidence/P07/live-usage.md`) |
| Publishing | 10/12 | Real structurally checked EPUB/PDF/DOCX/Markdown, cover, metadata and manifests are persisted; EPUBCheck and Kindle preview remain pending (`evidence/P08/publishing.md`) |
| Art | 0/5 | pending |
| Telegram | 0/5 | pending |
| Operations | 2/6 | Peer-authenticated backup/archive check and runbook are evidenced; isolated restore and owned service lifecycle remain pending (`evidence/P10/`) |

Hard gates: H3 PASS from `evidence/P04/reconciliation-correction.md`; H1,
H2, H4–H9 remain NOT RUN. H4 now has real output and owner-review evidence but
still needs a restart-through-production proof; H8 remains unproven because no
image-generation turn was invoked. Independent critics remain unavailable in this
runtime; lead critiques are recorded at `evidence/P00/critique.md`,
`evidence/P01/critique.md`, `evidence/P02/critique.md`,
`evidence/P03/critique.md`, `evidence/P04/critique.md`,
`evidence/P05/critique.md`, `evidence/P06/critique.md` and
`evidence/P07/critique.md`, `evidence/P08/critique.md` and
`evidence/P05/production-seam-critique.md` and `evidence/P10/backup-critique.md`.
Final evidence/revision: integrated slice `d2f3cf7`; application delivery remains
partial because the listed external hard gates are not fabricated as passed.
