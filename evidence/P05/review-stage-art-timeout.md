# Failed mixed production/review probe

Date: 2026-09-19 (Asia/Kolkata)

Disposable run `f80e6186-cc88-48f3-b1b6-21da33c04f1b` included an art direction.
The outline succeeded, while the production task launched the bounded Codex
art subprocess and exhausted its execution budget across three attempts. The
production task ended `failed` with `worker_execution_failure`; the dependent
review task was then durably marked `failed` and emitted dependency failure
events. The run ended `failed` with no manuscript artifact claimed.

This is retained as negative recovery evidence: a failed upstream task cannot
leave a queued review task stranded. It is not counted as a successful review
run or image gate.
