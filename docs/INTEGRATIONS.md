# Pi, providers, usage, Codex art and Telegram

## Pi boundary

Observed installed package in this conversation: `@earendil-works/pi-coding-agent@0.79.6`. Reverify/pin before coding; Context7 examples include older APIs. Pi owns provider login/refresh/model resolution, streaming, tools and session primitives. App owns persistence, queue, scoped authority and review decisions.

Global catalog/auth may be reused by the trusted host adapter. Use explicit resources to load only the model/provider adapter and approved MCP adapter; no inherited coding prompts, arbitrary global tools, skills or extensions. Store application sessions separately. Use Pi credential APIs/locking; do not implement ad hoc token refresh or copy credentials into logs/DB. Dashboard settings default to an app-specific overlay, with explicit action required to alter global configuration.

### Trusted KDP workflow reference

The KDP workflow references were installed with Skillfish from
`queelius/claude-anvil`: `kdp-publish` at
`8b451755e4945502c24ee97e95f068728543f59d`, `kdp-audit` at
`c79a117f55216b00004b95efdc01e2c6f365629a`, and `kdp-listing` at
`6f891605d8f0e6484bd764136a81ed874e646680`. The installed copies are
currently at `~/.codex/skills/kdp-{publish,audit,listing}` and contain only
reviewed `SKILL.md` files; no executable scripts, extensions or MCP servers
were installed with them.

The systemd worker sets
`EBOOK_FACTORY_ORCHESTRATOR_SKILL_PATHS` to the three explicit directories.
The Pi adapter still passes `--no-skills` and then explicitly adds those paths
only for the main orchestrator queue. Production child workers receive no
skill path. This keeps global skill discovery, inherited prompts and arbitrary
tools out of production execution.

The reference is advisory, not an authorization boundary. It helps the main
orchestrator explain and sequence KDP audit, listing, preparation, preview and
owner-controlled submission, but the worker has no browser/filesystem tools.
It must not claim to have run the referenced `/kdp-audit` or `/kdp-listing`
skills, and it must not upload to KDP, change account/tax/bank settings, buy a
proof, enroll in KDP Select, set pricing, or publish without a separate owner
decision. The source skill's referenced sibling skills are not present in the
installed copy; this is recorded as a capability gap rather than hidden
scaffolding.

Provider dashboard must list actual available models, auth status, last successful connection check, selected orchestration/drafting/review models, and configuration scope. Support subscription login/reconnect through Pi-supported flows, API key save/remove and custom endpoint/model setup. Custom URLs are explicit operator configuration, support local endpoints, and require transport/protocol choice and a real call test. Never forward credentials across redirect origins. Store secrets through Pi's credential mechanism with restricted file permissions, or an encrypted app vault with key outside DB; never return them from GET APIs. Model switching affects new attempts only.

## Usage: exact when observed, honest when unavailable

Track each call with call_id, provider_request_id if supplied, project/run/task/attempt/session/agent IDs, purpose, model, provider/account alias, start/end, outcome, input/output/cache-read/cache-write/reasoning tokens, price version, estimated cost, reported billed cost and provider credit units. Nullable fields mean unknown. Store normalization version and sanitized source metadata.

Pi streaming usage can be cumulative. Upsert one current aggregate per call/message and finalize once; never sum every streaming update. Preserve finalization/correction events. Retries and failed calls with reported usage count separately. Parent totals roll up children once; never add both parent aggregate and child usage rows. Normalize cache/reasoning inclusion per provider to avoid double counting. A zero catalog price is not evidence that a subscription request was free.

Expose three distinct figures: provider-reported consumption, estimated API-equivalent cost with dated unit prices, and actual billed money when supplied. Subscription cost is not reconstructed from tokens. GitHub credit/premium-request multipliers and conversions require provider evidence. Account-wide quota changes may include unrelated Pi/Codex activity and must not be assigned to a book.

Quota snapshot: provider/account/bucket, source, observed_at, stale_after, used/remaining, units, window length, resets_at, plan label, capability state (supported/unavailable/auth_required/stale), error. Render real returned windows; never hardcode every account to five hours. Refresh on provider feedback and a bounded periodic interval, not per streaming token. Show stale age and a provider-dashboard link when unsupported.

Codex official app-server documents `account/rateLimits/read` and `account/rateLimits/updated`; version-probe the installed server. GitHub documents quota and billing in its own Copilot SDK; this does NOT prove Pi emits those fields. Prefer Pi metadata; a small read-only quota adapter may use an officially supported provider surface if compatible with existing auth. No second generation runtime and no scraping undocumented endpoints as a hidden dependency.

Required capability spike outputs: installed versions; emitted usage fields for one real Pi call; deduplication proof with replay; quota source/schema/status for Codex and Copilot; unsupported fields explicitly listed. Dashboard still works if account counters are unavailable, but record the gap and award only rubric credit actually earned. Budget enforcement uses measured/estimated usage with labels and reserved headroom; unknown money uses token/turn/time caps. No silent provider switching to incur charges.

## Codex subscription image tool

Use Codex as a bounded tool called by Pi, not a second orchestrator or OpenAI Agents SDK. The owner's subscription image ability is accepted; unattended integration remains unverified. Probe installed Codex CLI/app-server capabilities and official docs before selecting a route. Demonstrate actual image output, save bytes in job storage, decode/check them, record provenance and usage availability. Receiving text describing an image is a failure.

Do not assume the interactive Codex tool available in this assistant session is exported to arbitrary programs. Do not assume the label `images=yes` in Pi means generation. If no callable subscription route is available, report the limitation early, keep a cover import tool, and continue other work. Manual art fallback does not satisfy the automated-art completion gate. Never silently add paid image API use.

Separate generated illustration from deterministic cover typography/layout. Keep art prompt/revision, generation source, original asset, layout template and final ebook cover so the owner can revise text without paying for a new image.

## Telegram

Single bot/channel, long polling; same application conversation and orchestrator. Token supplied via private env/file, plus allowed chat AND sender IDs. Persist processed update IDs and advance polling offset only after durable receipt. A second adapter instance cannot consume updates concurrently. Incoming messages enqueue the same conversation turns as dashboard messages; serialize ordering and dedupe replays.

Commands: /projects, /use, /status, /pause, /resume, /cancel plus free-text chat and approval buttons. Bind every approval callback to project, revision and one-time decision ID; stale/duplicate decisions return the existing result. Owner should not see child-agent chats. Progress notifications are milestone-based, not token spam.

Persist outgoing notifications in an outbox. Retry failures with bounded backoff; delivery uncertainty may cause duplicates (Telegram send is not assumed exactly-once), so include a stable job/event label. Split long messages safely, redact secrets. Private local artifact links are not accessible from Telegram remotely; send approved small files directly within current Bot API limits or offer dashboard access, never publish files to a public host automatically.

Missing token/IDs leaves Telegram visibly unconfigured and the build incomplete for that gate; never test against arbitrary chats.
