# Delivery Gap Reconciliation Plan

## Objective

Review the deployed candidate `codex/ebook-factory-v2` at `f04effc` (runtime
transport change `88f7680`), follow the
actual ebook journey, close every defect that can be completed without owner
credentials or paid external actions, and leave an evidence-backed handoff for
the remaining gates.

## Work completed or in progress

1. Confirm candidate identity, service ownership and readiness on the host.
2. Run the full verification and acceptance entry points from the candidate
   worktree.
3. Keep recovery tests from ever falling back to the live PostgreSQL database;
   add a regression test for that safety contract.
4. Make acceptance evidence discovery use the current Telegram evidence name
   instead of a stale legacy filename.
5. Exercise an isolated, provider-free ebook journey through the real API
   boundaries: brief, approval, outline, section drafts, assembly, review,
   export and owner revision.
6. Repair defects found by that journey with red/green regression tests:
   normalize SQLite lease timestamps and export the complete dependency-fenced
   manuscript rather than the first section only.
7. Update publishing guidance and evidence to distinguish structural validation
   from Kindle visual preview and owner art review.

## Remaining external gates

### Kindle preview

The package is structurally validated, and the exporter now also enforces the
current under-50 MB marketing-cover limit alongside RGB/1600×2560 geometry. Kindle
visual preview is still a separate gate. Amazon's current documentation says
Kindle Previewer is a free desktop app for Windows 8.1+ and macOS 10.15+,
accepts EPUB, and can inspect devices, orientations, fonts, images, lists and a
full auto-advance pass. KDP's Online Previewer is the best fit for this Linux host:
it runs from an authorized KDP Bookshelf draft and previews tablet, phone and
Kindle-reader modes, including a quality check.

Recommended order:

1. Owner opens `http://192.168.29.14:6969`, downloads the final `book.epub`,
   records its SHA-256, and uploads it to a private/unpublished KDP draft only
   for preview. Do not click publish.
2. Run the Online Previewer on phone, tablet and Kindle-reader modes; inspect
   cover/title page, TOC, opening/middle/end chapters, long headings, lists,
   links, images and any citations. Run the quality check and record defects.
3. If desktop access is easier, use the current Kindle Previewer desktop app
   on Windows or macOS with the same hash and record the version,
   device/orientation/font matrix and auto-advance result.
4. Fix any defects in Ebook Factory, regenerate a new immutable package, and
   repeat. Record `kindle_preview_verified` only against the exact final hash.

EPUBCheck and local reader rendering remain useful preflight checks but cannot
be relabelled as Kindle certification. Do not upload or publish automatically.

### Live owner art review

The generated image and durable review UI are present, but only the owner can
decide `Approve` or `Request revision`. The live source image is a valid PNG
(1,385,196 bytes, SHA-256
`51dc6b93c3fe9b3a83d91572b66b1419d9cde9c4bc59da8fef67bcb6b4bdb1f0`) and is
visually an abstract blue horizon/star composition without cover typography;
that is an agent observation, not an owner approval. The selected source image
must be reviewed by hash in the dashboard. Approval permits export; a revision
request preserves the old image and blocks stale package reuse.

Recommended decision sequence:

1. Open the dashboard over the LAN URL, select the art-bearing project and
   inspect the source image at full size plus its intended cover layout.
2. Choose `Approve` if the composition is acceptable as the illustration, then
   create a new export so the package records the approved source and final
   cover hash.
3. Choose `Request revision` with a concrete note if the image, composition or
   intended audience is not acceptable. The previous image remains immutable;
   regenerate only after the note is recorded, then review the replacement.

This action is intentionally not automated: it is the product's human quality
and rights checkpoint, and the image's visual suitability cannot be inferred
from PNG validity or a model-generated description.

### Usage, billing and quotas

Keep observed token usage, estimated cost, provider-reported billing, and
subscription allowance as separate fields. Treat unavailable monetary billing
and unsupported Copilot quota as `unknown`, never zero. The live Codex quota
adapter may report account windows, but it is not a monetary billing source.
Only add a provider billing integration when an official, authorized source is
available.

Best default for this personal installation: keep the current live Codex quota
windows and per-call lineage, show token totals and `billing unknown`, and do
not spend credits to chase an unsupported billing number. Copilot quota is an
independent provider capability and should remain explicitly unavailable unless
you choose to configure and authorize its official quota surface. If you want
cost estimates later, add dated provider price tables as estimates only; never
convert subscription usage into claimed billed money.

The remaining usage evidence gap is not a missing UI feature: it is the lack of
an authorized, official monetary-billing source and Copilot quota source. No
safe local change can manufacture either observation.

### Owner decisions that remain

| Decision | Best option | What it closes |
|---|---|---|
| Kindle validation | KDP Online Previewer from an unpublished draft | Kindle visual-preview evidence for the exact EPUB hash |
| Art quality | Owner approves or requests revision in the dashboard | Live owner-art decision; approval enables a final export |
| Billing | Keep money as unknown; retain measured tokens and live Codex windows | Honest usage accounting without spending or fabricating billing |
| Copilot quota | Leave unsupported unless separately authorized | No product need for a second provider's account integration |

Only the first two rows require an owner action for this build. The latter two
are policy choices; the current implementation already behaves safely under the
recommended options.

### Custom provider

If the owner supplies an authorized OpenAI-compatible endpoint and key, run one
real connection test and one attributed call through the configured boundary.
Without that external endpoint, retain the local protocol checks as partial
evidence and do not award the real-provider points.

### Telegram live click

The durable project menu and routing are implemented. A final owner trace still
needs `/help`, one inline project selection, a plain message, replay, and (if
desired) a restart check in the configured chat. Test callbacks are not a
substitute for that owner action.

## Final verification

- Run focused export/production tests and the complete `make verify` suite.
- Run `make acceptance`; retain its truthful partial exit while external gates
  remain open.
- Run the security/secret checks without reading or committing `.env`.
- Restart only the owned API service after the final commit, then verify both
  `http://192.168.29.14:6969/ready` and the local readiness endpoint. Verify
  the Tailscale listener separately with HTTPS when needed.
- Append a lead ledger row with the final revision, evidence, result and
  unresolved owner decisions.
