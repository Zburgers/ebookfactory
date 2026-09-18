# Delivery scorecard

Current score: **72/100 — durable runtime/containment, real production with
reviewed revision lineage, live usage attribution, dashboard document flow and
structural publishing packages are evidenced; external hard gates remain.**

| Area | Earned / available | Evidence |
|---|---:|---|
| Pi/providers | 4/10 | Real Luna-low subscription call with provider/model/usage attribution; custom URL/key protocol integration and a browser-driven provider connection check remain pending (`evidence/P07/live-usage.md`) |
| Durable runtime | 14/14 | `evidence/P02/integration.md`; real PostgreSQL recovery suite covers atomic enqueue/dedupe, restart/checkpoint recovery, fencing, cancellation and concurrent claims |
| Containment | 10/10 | Filesystem/secret isolation, enforced network/resource limits and label-scoped reconciliation all pass P04 evidence, including unrelated-container preservation |
| Production | 14/16 | Real fiction/nonfiction output, fenced context/task lineage, owner revision and a resolved review finding are evidenced; durable budget blocking is implemented but its live rejection subcriterion remains unawarded (`evidence/P05/real-production.md`, `evidence/P05/budget-blocking.md`, `evidence/P06/dashboard-correction.md`) |
| Dashboard | 10/10 | Real Chromium journey covered chat/brief/review, replayed events, section editing, ten export/download links, quota/settings visibility and accessibility checks (`evidence/P06/dashboard-browser-trace.md`) |
| Usage | 8/12 | Real finalized call attribution, idempotent totals, live redacted Codex subscription windows, explicit stale/unknown states and project-scoped call drill-down are evidenced; estimates and Copilot quota remain pending (`evidence/P07/live-usage.md`, `evidence/P07/quota-live.md`, `evidence/P07/usage-drilldown.md`) |
| Publishing | 10/12 | Real structurally checked EPUB/PDF/DOCX/Markdown, cover, metadata and manifests are persisted; EPUBCheck and Kindle preview remain pending (`evidence/P08/publishing.md`) |
| Art | 0/5 | pending |
| Telegram | 0/5 | Durable adapter and redacted status boundary are implemented and tested; live token/chat/sender loop remains pending (`evidence/P09/telegram.md`) |
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
Final evidence/revision: integrated slice `e15ceb1` (with Telegram at `ba181f7`);
application delivery remains
partial because the listed external hard gates are not fabricated as passed.
