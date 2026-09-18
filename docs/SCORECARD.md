# Delivery scorecard

Current score: **34/100 — P02 durable-runtime, P04 containment, and the
host-side real fiction/nonfiction production slice are evidenced; the
integrated product and hard gates are not complete.**

| Area | Earned / available | Evidence |
|---|---:|---|
| Pi/providers | 0/10 | P00 CLI spike plus P03 non-secret provider/capability boundaries; no dashboard-configured live response or usage persistence yet (`evidence/P03/`) |
| Durable runtime | 14/14 | `evidence/P02/integration.md`; real PostgreSQL recovery suite covers atomic enqueue/dedupe, restart/checkpoint recovery, fencing, cancellation and concurrent claims |
| Containment | 10/10 | Filesystem/secret isolation, enforced network/resource limits and label-scoped reconciliation all pass P04 evidence, including unrelated-container preservation |
| Production | 10/16 | Real readable fiction and nonfiction artifacts, fenced context, task lineage and draft-review state are evidenced; owner revision/editorial repair and budget-block behavior remain pending (`evidence/P05/real-production.md`) |
| Dashboard | 0/10 | P06 same-origin shell boots and exposes project/chat/approval/event flows, but full review/edit/download/browser journey is not yet evidenced (`evidence/P06/`) |
| Usage | 0/12 | P07 replay-safe accounting primitive keeps cost unknown rather than zero, but live provider attribution/quota evidence is pending (`evidence/P07/`) |
| Publishing | 0/12 | P08 artifact validation and Markdown rendering are tested, but no validated EPUB/PDF/DOCX package or Kindle evidence exists (`evidence/P08/`) |
| Art | 0/5 | pending |
| Telegram | 0/5 | pending |
| Operations | 0/6 | P10 now has a real peer-authenticated backup/archive check and runbook, but isolated restore and owned service lifecycle are not evidenced (`evidence/P10/`) |

Hard gates: H3 PASS from `evidence/P04/reconciliation-correction.md`; H1,
H2, H4–H9 remain NOT RUN. The real production slice does not pass H4 by itself
because owner revision/prior-version review is still missing. Independent critics remain unavailable in this
runtime; lead critiques are recorded at `evidence/P00/critique.md`,
`evidence/P01/critique.md`, `evidence/P02/critique.md`,
`evidence/P03/critique.md`, `evidence/P04/critique.md`,
`evidence/P05/critique.md`, `evidence/P06/critique.md` and
`evidence/P07/critique.md`, `evidence/P08/critique.md` and
`evidence/P05/production-seam-critique.md` and `evidence/P10/backup-critique.md`.
Final evidence/revision: P05 real production evidence is the latest
implementation slice; integrated application delivery remains partial.
