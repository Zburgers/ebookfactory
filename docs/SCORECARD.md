# Delivery scorecard

Current score: **21/100 — P02 durable-runtime and the tested P04 containment
subcriteria are evidenced; the integrated product and hard gates are not
complete.**

| Area | Earned / available | Evidence |
|---|---:|---|
| Pi/providers | 0/10 | P00 CLI spike plus P03 non-secret provider/capability boundaries; no dashboard-configured live response or usage persistence yet (`evidence/P03/`) |
| Durable runtime | 14/14 | `evidence/P02/integration.md`; real PostgreSQL recovery suite covers atomic enqueue/dedupe, restart/checkpoint recovery, fencing, cancellation and concurrent claims |
| Containment | 7/10 | Filesystem/secret isolation and enforced network/resource limits pass `evidence/P04/integration.md`; reconciliation/cleanup subcriterion remains pending |
| Production | 0/16 | P05 now has a fenced context/Pi runner seam, but no real fiction/nonfiction book or autonomous production run is claimed (`evidence/P05/`) |
| Dashboard | 0/10 | P06 same-origin shell boots and exposes project/chat/approval/event flows, but full review/edit/download/browser journey is not yet evidenced (`evidence/P06/`) |
| Usage | 0/12 | P07 replay-safe accounting primitive keeps cost unknown rather than zero, but live provider attribution/quota evidence is pending (`evidence/P07/`) |
| Publishing | 0/12 | P08 artifact validation and Markdown rendering are tested, but no validated EPUB/PDF/DOCX package or Kindle evidence exists (`evidence/P08/`) |
| Art | 0/5 | pending |
| Telegram | 0/5 | pending |
| Operations | 0/6 | P10 now has a real peer-authenticated backup/archive check and runbook, but isolated restore and owned service lifecycle are not evidenced (`evidence/P10/`) |

Hard gates H1–H9: NOT RUN. Independent critics remain unavailable in this
runtime; lead critiques are recorded at `evidence/P00/critique.md`,
`evidence/P01/critique.md`, `evidence/P02/critique.md`,
`evidence/P03/critique.md`, `evidence/P04/critique.md`,
`evidence/P05/critique.md`, `evidence/P06/critique.md` and
`evidence/P07/critique.md`, `evidence/P08/critique.md` and
`evidence/P05/production-seam-critique.md` and `evidence/P10/backup-critique.md`.
Final evidence/revision: P10 backup `ba9a18a` is the latest
implementation; integrated application delivery remains unimplemented.
