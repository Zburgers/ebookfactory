# Delivery Gap Reconciliation Plan

## Objective

Review the deployed candidate `codex/ebook-factory-v2` at `bf8230b`, follow the
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

The package is structurally validated, but Kindle visual preview is a separate
gate. The preferred options are:

- Owner runs Kindle Previewer 4 on supported Windows/macOS and records the exact
  EPUB hash, version, device/orientation checks and any defects.
- Owner uses KDP's online preview surface with the authorized account and
  records the same evidence.

EPUBCheck and local reader rendering remain useful preflight checks but cannot
be relabelled as Kindle certification. Do not upload or publish automatically.

### Live owner art review

The generated image and durable review UI are present, but only the owner can
decide `Approve` or `Request revision`. The selected source image must be
reviewed by hash in the dashboard. Approval permits export; a revision request
must preserve the old image and block stale package reuse.

### Usage, billing and quotas

Keep observed token usage, estimated cost, provider-reported billing, and
subscription allowance as separate fields. Treat unavailable monetary billing
and unsupported Copilot quota as `unknown`, never zero. The live Codex quota
adapter may report account windows, but it is not a monetary billing source.
Only add a provider billing integration when an official, authorized source is
available.

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
