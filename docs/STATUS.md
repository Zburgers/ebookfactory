# Build status

2026-09-18: P00 capability discovery, P01 runnable skeleton and P02 durable
jobs/events are implemented on the isolated branch. P01 revision `89673c6` provides the FastAPI health and
readiness service, pinned Python dependencies, shared JSON/OpenAPI contracts,
SQLAlchemy metadata and Alembic migrations. The owner-authorized PostgreSQL
target is `ebookfactory` with peer role `naki`; migrations are at head
`3c2a5f8e1b4d` and the real readiness check returned `ok`. The P00 report at
`evidence/P00/capabilities.json` records Pi 0.85.1,
Codex CLI 0.155.0, rootless Podman 4.9.3 and PostgreSQL client 16.15. A real
Pi CLI probe returned usage fields from `openai-codex` / `gpt-5.5`; this is not
yet dashboard evidence. No Telegram credentials were supplied or
image-artifact route proven. P02 revision `a0ca026` adds hash-bound approval,
durable jobs, lease/fencing recovery, cancellation epochs, ordered event/outbox
replay, private worker callbacks and a minimal supervisor loop. Six focused
PostgreSQL recovery tests pass, including concurrent claim ownership; P03–P10
remain incomplete. P03 revision `8de7198` adds durable project conversations,
message dedupe/order, non-secret provider metadata, capability-token scope
checks, and explicit Pi CLI resource flags. It does not claim a live dashboard
provider response. P04 revision `58e1161` adds a pinned non-root rootless
Podman image, private workspace arguments and a real host-sentinel/network
containment check. Artifact validation and crash reconciliation are still
pending. P05 revision `c3cbf4c` adds the revisioned brief/section/review
document core and API journey checks, but not a generated book or production
runner. P06 revision `89640b4` adds a same-origin dashboard shell with project,
chat, approval, event-cursor and provider metadata flows; full review/download
dashboard acceptance remains pending. Generated dashboard API artifacts were
committed in follow-up revision `c0b0bfb`.
P07 revision `b2e1d5a` adds replay-safe usage-call recording/finalization and
explicit null cost fields, but no live Pi call or quota adapter is wired yet.
P08 revision `bd9e6c8` adds immutable artifact path/hash/size validation and
deterministic Markdown rendering; installed converter/EPUBCheck gaps keep the
publishing package incomplete. P05 follow-up revision `60af606` adds the
fenced worker context endpoint and low-thinking, no-tools Pi runner seam. The
current follow-up adds fenced production-result/artifact acceptance,
provider/model lineage and authoritative Pi JSON `message_end` parsing; two
real low-thinking Luna runs (fiction and nonfiction) are recorded in
`evidence/P05/real-production.md`.
P06 follow-up `54635c5` adds a tested bounded replay SSE endpoint; the shell
still polls JSON until live relay work is complete.
P10 revision `ba9a18a` adds a peer-authenticated custom-format backup,
non-destructive archive check and local runbook; isolated restore and owned
service lifecycle remain pending. P04 follow-up `9f87d3e` adds real
label-scoped container reconciliation and unrelated-container preservation.

Next: finish review-aware production and integrate the validated publishing
package into the dashboard. P07 now has one real finalized usage call and P08
has real fiction/nonfiction packages; P08 art capability is proven but no
image-generation turn has been invoked. Integrated revision `d2f3cf7` adds the
review-aware section editor, owner revision/export flow, real finalized usage
attribution, deterministic EPUB/PDF/DOCX/Markdown packages, project-scoped
review ownership checks, and the Codex app-server art adapter. The Python
dependency audit is clean after upgrading Pillow to 12.3.0. P09 revision
`ba181f7` adds durable allowlisted Telegram receipt/link/outbox state and a
redacted status boundary; the live bot remains unconfigured. Pending owner
input: Telegram token and allowed chat/sender IDs. Pending technical proofs: Pi
model gateway inside containment, Codex subscription image bridge, provider
quota availability, EPUBCheck/Kindle preview, a real Codex image artifact,
Telegram loop, isolated restore, and the rest of the integrated product. P10
revision `e15ceb1` adds runnable `make acceptance` and `make restore-check`
entrypoints; target composition was corrected in `1a7c100`, and acceptance
deliberately exits PARTIAL while those gates remain unproven.
Production revision `f04fd56` adds durable measured budget blocking for turn,
token and elapsed-time caps; the focused transition test passes, while a live
provider rejection remains intentionally unspent/unproven.

Operating instruction: for future probes and delegated work, explicitly select
the least-cost available route, preferably GPT 5.6 Luna low when the runtime
actually exposes it; record the selected model/effort and never infer it from
a catalog name.

Maintain this as a short current-state summary; preserve activity history in AGENT_LEDGER.md.
