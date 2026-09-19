# Build status

2026-09-19: A real disposable production restart probe reclaimed one job from
fencing generation 1 to generation 2 after the worker service was killed and
automatically restarted. The probe then found an unbounded Codex art
app-server subprocess; the run was cancelled durably before retry. The
follow-up adds a 120-second timeout, parent abort handling and bounded redacted
errors with process-group SIGTERM/SIGKILL escalation and eleven focused tests.
H2/H4 are not claimed from this failed probe;
evidence is at `evidence/P05/restart-live.md`.

2026-09-19: Independent re-review of the page/artifact packet found six
concrete gaps. Revision `6cfdb5d` repairs four: page-target manuscripts now
enforce estimated 100–180 words/page bounds, downloads verify SHA-256 as well
as size, OpenAPI describes the provider connection-test policy, and the Pi
runner flushes an unterminated final JSONL event. The earlier `c53c700` repair
normalizes Codex art usage keys before persistence. The default self-signed TLS
identity remains a separate transport-trust finding; the page workflow still
lacks a real 50–150 page provider run and the score remains conservative.

2026-09-19: The page-target prompt now matches the validator contract: it
states 100–180 words per page, derives 5,000–27,000 words for a 50–150 page
request, and asks for an 8–15 sectioned manuscript. Focused worker tests pass;
no provider was invoked for this repair.

2026-09-19: Revisions `c5e05e9`, `205d1ca` and `e2fcd8e` extend the durable
book path. Studio now submits a selected 50–150 page target (or an explicit
word range), the API rejects reversed ranges, and project artifacts have
project-scoped metadata, previews/downloads and immutable path checks. Codex
app-server image calls now carry their generated call ID and reported usage;
the production callback records a separate `art` usage row when available.
Focused artifact, recovery, worker-art and contract checks pass. These changes
still do not claim a real 50–150 page provider run or EPUBCheck/Kindle proof.

2026-09-19: Revision `952bfc2` closes the dashboard token-streaming hole at
the durable boundary. Pi JSON `message_update` text deltas are forwarded by
the trusted worker, fenced by turn generation, persisted as replayable events,
and rendered by an authenticated reconnecting SSE reader; the final
`message_end` remains authoritative. The live no-provider-cost integration
check is recorded at `evidence/P06/streaming-live.md`. The same follow-up
adds shared short-lived login throttling, stronger durable failure redaction,
and accurate OpenAPI owner/worker/capability metadata. Non-loopback port 6969
listeners now use TLS while loopback remains HTTP for the local worker.
Default TLS is self-signed and therefore does not prove server identity until
the certificate is trusted or replaced. This remains a transport security
finding, separate from the H1 provider-call definition. The 50–150 page path is staged but still lacks a
real long-book run, Telegram same-conversation proof, art usage attribution,
and restart-through-production evidence.

2026-09-19: Revisions `1508766` and `25268b1` repair the live Codex
app-server art boundary: current snake_case `saved_path` events are accepted,
provider-qualified model names are normalized at `thread/start`, and focused
red/green tests cover both. Revision `3a029c7` makes project artifact listing
include production-run outputs, so generated covers appear in the dashboard.
A real integrated production run completed after bounded retries and
persisted a 1.38 MB PNG with hash evidence in `evidence/P08/art-live.md`.
H8 is now PASS; H4/H5/H2 and the 50–150 page staged workflow remain open.
The affected focused checks pass, and `make verify` passes with 61 Python
tests plus the worker, service, recovery, migration, containment and Telegram
behavior checks. The live quota response continues to be fetched from
`codexctl status` per request; its values are intentionally time-sensitive.
Revision `a433983` additionally retains all valid live CLI accounts as
redacted account indexes and labels multiple-account windows in the dashboard.
The latest independent hole audit is NO-GO: its actual runtime was GPT-5
Codex rather than the requested Luna-high override, so Luna identity is not
claimed for that audit.

2026-09-19: Revision `2ad955e` adds a durable dashboard-to-Pi orchestrator
worker and an on-demand Codex quota adapter. `GET /quota/live` invokes the
local `codexctl status` command per request, parses only verified 5-hour and
7-day windows, and returns explicit 503/unavailable behavior without writing
quota rows. The Usage panel now shows readable live windows, source and fetch
time, and no `unknown%` placeholders. The rootless worker service is enabled
for boot under `naki`; a real dashboard turn completed through
`openai-codex/gpt-5.6-luna` and persisted the assistant response. Evidence is
at `evidence/P07/quota-on-demand.md` and `evidence/P06/orchestrator-live.md`.
The independent Luna-high critique remains NO-GO for the full product gate:
token streaming, bounded failure state, turn-scoped context, Telegram routing,
owner authentication, and stable browser dedupe remain open.

2026-09-19: The owner raised the completion gate from `>80/100` to strictly
`>90/100` (at least 91), with all hard gates unchanged. P10 now installs the
API as rootless `ebook-factory-api.service` under the `naki` user manager,
enabled for boot with `Linger=yes`, automatic failure restart, and port 6969
bound only to loopback, the current Tailscale IPv4, and the explicit `eno1`
private-LAN IPv4. Real health checks passed on
`127.0.0.1:6969`, `100.87.104.100:6969`, and `192.168.29.14:6969`; a
deliberate main-process kill was recovered by systemd. Revision `ca7d6bc` also
adds a worker-token/local-only provider connection test with pinned-address
dialing, exact-origin private allowlisting, and no secret-bearing responses;
see `evidence/P03/provider-connection.md` and `evidence/P10/systemd-service.md`.
The score is now 78/100 after H9 isolated restore evidence was added at
`evidence/P10/isolated-restore.md`. Telegram, Codex image, Copilot billing and
Kindle/EPUBCheck gates remain pending.

2026-09-19: P05 worker follow-up `0e691d0` hardens the trusted supervisor with
lease heartbeats, fenced completion/failure callbacks, bounded mutation/claim
backoff, stale-lease cancellation, abort-aware HTTP requests and schema-shaped
behavior checks. Full verification passes, but H2 remains unclaimed until a
real Podman-mediated production worker survives process restart.

2026-09-18: P00 capability discovery, P01 runnable skeleton and P02 durable
jobs/events are implemented on the isolated branch. P01 revision `89673c6` provides the FastAPI health and
readiness service, pinned Python dependencies, shared JSON/OpenAPI contracts,
SQLAlchemy metadata and Alembic migrations. The owner-authorized PostgreSQL
target is `ebookfactory` with peer role `naki`; migrations are at head
`8b4e6c7d9a10` and the real readiness check returned `ok`. The P00 report at
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
model gateway inside containment, Codex subscription image bridge, Copilot
quota/provider billing, EPUBCheck/Kindle preview, a real Codex image artifact,
Telegram loop, isolated restore, and the rest of the integrated product. P10
revision `e15ceb1` adds runnable `make acceptance` and `make restore-check`
entrypoints; target composition was corrected in `1a7c100`, and acceptance
deliberately exits PARTIAL while those gates remain unproven.
Provider follow-up `ca7d6bc` adds real local-HTTP OpenAI-compatible and health
protocol connection checks, strict credential-reference validation, pinned DNS
resolution, redirect/proxy avoidance, response usage filtering, and dashboard
controls. The full verification suite and independent Luna-low security review
pass; H1 still requires a real dashboard-configured Pi answer.
Operations follow-up `5f9c918` adds a collision-safe isolated PostgreSQL
restore check and real archive restore evidence. H9 is marked PASS; the
requested Luna-high critic capability was unavailable, while a separate
Luna-low critic found no remaining critical/high/medium findings.
Operations follow-up `a20f00f` adds an owned API/dashboard lifecycle wrapper
with readiness wait, PID ownership checks and Make start/stop/restart/status
commands. Worker/container lifecycle remains a separate unclaimed boundary.
Production revision `f04fd56` adds durable measured budget blocking for turn,
token and elapsed-time caps; the focused transition test and the later live
API boundary rejection pass. Provider-side rejection remains intentionally
unspent/unproven. A real
PostgreSQL/API boundary check rejected an over-budget production result before
publication and recorded the blocked transition in `evidence/P05/budget-live.md`.
Quota follow-up `530de4e` adds a Codex app-server rate-limit parser, authenticated
snapshot ingestion, stale/unavailable semantics and a dashboard Usage panel.
A read-only real subscription probe persisted primary 30% used, secondary 26%
used and an unavailable credits record without retaining provider account IDs.
Usage quota evidence earns the Codex quota subcriterion; Copilot quota and
monetary billing remain unknown.
Dashboard follow-up `e37c2ae` records a real Chromium owner journey over
PostgreSQL: synthetic chat/brief/approval, section revision, review display,
ten export links/download, event replay, quota/settings visibility and
accessibility checks. The synthetic queued run was cancelled after the trace;
no model call was made.
Usage follow-up `e68807f` adds project-scoped call drill-down to the API and
dashboard. The real Luna usage project now shows its persisted call lineage,
tokens and outcome while monetary billing remains explicitly unknown.

Operating instruction: for future probes and delegated work, explicitly select
the least-cost available route, preferably GPT 5.6 Luna low when the runtime
actually exposes it; record the selected model/effort and never infer it from
a catalog name.

Maintain this as a short current-state summary; preserve activity history in AGENT_LEDGER.md.
