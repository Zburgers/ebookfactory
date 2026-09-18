# Evidence-based completion

Completion must be **strictly greater than 80/100**, meaning at least 81, AND all hard gates pass. Score is functional delivery; critic confidence is a separate judgment. Do not average away a failed independent run. Missing evidence scores zero. Full scope is 100 and remains the objective.

## Weighted rubric

Each subcriterion is binary: award its listed points only when its behavior and evidence pass. No arbitrary fractional self-grading.

| Area | Subcriteria | Points |
|---|---|---:|
| Pi/providers | real subscription call 4; catalog/model config 3; custom URL/key real protocol integration 3 | 10 |
| Durable runtime | atomic enqueue/dedupe 4; restart/checkpoint recovery 5; fencing/cancel/concurrent claim 5 | 14 |
| Containment | filesystem/secret isolation 4; enforced network/resource limits 3; precise reconciliation/cleanup 3 | 10 |
| Production | fiction and nonfiction real output 6; bounded delegation/context/lineage 4; editorial repair and owner revision 4; budget/block behavior 2 | 16 |
| Dashboard | chat/brief/review 4; replayable task monitoring 3; editing/downloads/accessibility 3 | 10 |
| Usage | call attribution/deduped totals 4; estimates vs reported billing 2; Codex quota supported/live 2; Copilot quota supported/live 2; stale/unknown and drilldown 2 | 12 |
| Publishing | valid EPUB/DOCX/PDF/Markdown 5; metadata/provenance/manifest 3; reader checks 2; Kindle preview evidence 2 | 12 |
| Art | automated subscription output 3; review/revision/layout/provenance 2 | 5 |
| Telegram | live same-conversation loop 3; dedupe/allowlist/revision-bound decisions 2 | 5 |
| Operations | service lifecycle 2; backup/isolated restore 2; reproducible handoff/docs 2 | 6 |
| Total | | 100 |

## Hard gates (cannot be traded for points)

H1: One real Pi provider call from dashboard configuration, with recorded model and usage capability status.

H2: Production survives browser close AND worker restart; duplicate approvals don't duplicate work; expired/cancelled attempts cannot publish.

H3: Real rootless execution denies host sentinel access and unauthorized network reach; no global home/auth mount, secrets in evidence, or unrelated teardown.

H4: An approved brief produces a complete, readable short book through autonomous tasks, then supports an owner revision with prior versions intact. Both fiction and nonfiction profile checks are run. Mock text is not acceptance.

H5: Usable dashboard conversation/review/progress plus live Telegram same-conversation delivery and deduplication with owner-configured credentials.

H6: Usage captures calls/children/retries without double counting. Unknown account quota or monetary cost is explicitly unknown, not zero. Unsupported provider quota alone need not block the product but loses corresponding rubric points and remains an explicit limitation.

H7: Actual structurally validated EPUB, PDF, DOCX and Markdown package with accurate cover/metadata/provenance and immutable hashes. Kindle visual preview pending must be prominent; no claim of Amazon certification without preview evidence.

H8: Real subscription-backed Codex image output through the bounded tool. Manual import is a useful fallback but does not pass this requirement without an explicit owner scope change.

H9: Backup restore demonstrated into an isolated target; exact delivery revision and source/evidence references retained; no unresolved critical/high correctness or containment findings.

## Evidence format

Each check records UTC, code revision, runtime versions, target identity, command or browser actions, expected result, observed result and artifact paths/hashes. Use synthetic non-sensitive book briefs for acceptance and never capture credentials. Test doubles may cover fault injection; they cannot establish real provider/Telegram/image success.

Critic report per packet: findings ordered by severity, exact evidence, pass/fail subcriteria, confidence 0–100 with reason. Lead final report: total score, hard-gate matrix, completed/deferred/blocked items and how to run/recover. Critic must verify all claimed high-risk successes against the same delivered revision. A scaffold or test fixture passing is not a running product.

## Stop conditions

Continue implement/critique/repair until requested scope is delivered and mandatory gates pass. If a missing credential, unsupported subscription interface or owner choice prevents progress, do all independent work, preserve evidence, report PARTIAL/BLOCKED and request only the exact missing input. Never alter weights, redefine tests, suppress failures, or turn manual fallbacks into automated successes to cross 80.
