# Usage Cost Estimates and Application Loading States Implementation Plan

## Delivery status

Implemented in the current reconciliation slice. Source-attributed pricing,
cache-aware usage rollups, live GitHub billing reads, selector pricing labels,
workspace/project scope copy, artifact availability states, orchestrator trace
relay, and dashboard skeletons are integrated. Remaining results are external
by design: GitHub may return no billable personal record, and Kindle/owner-art
acceptance requires an owner-controlled external surface.

> **For Claude:** REQUIRED SUB-SKILL: Use shipyard:shipyard-executing-plans to implement this plan task-by-task.

**Goal:** Preserve the existing usage ledger while adding transparent model-priced token estimates, live GitHub Copilot billing when an owner-supplied PAT is present, Copilot AI-credit estimates, model/day rollups, and consistent loading skeletons across the dashboard.

**Architecture:** Keep project usage accounting durable in the existing `usage_calls` table. Add a pinned, source-attributed pricing registry that calculates known dimensions, and a read-only live GitHub billing adapter that reads a PAT from process environment without persisting it. Keep account-level official billing separate from project-local estimates and from Codex subscription usage, then render all three boundaries in the existing vanilla dashboard without adding a chart dependency. Add small reusable skeleton renderers in the dashboard and invoke them at every asynchronous loading boundary.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, vanilla ES modules, CSS, Node/Python tests.

---

### Task 1: Add source-attributed model pricing and cost math

**Files:**
- Create: `apps/api/app/pricing.py`
- Test: `apps/api/tests/test_usage.py`

**Steps:**
1. Write failing tests for OpenAI-equivalent and GitHub Copilot model prices, including uncached input, cache read, cache write, output, AI-credit conversion, unknown models, and long-context tier selection.
2. Run `pytest apps/api/tests/test_usage.py -q` and confirm the new tests fail because the pricing module/API does not exist.
3. Implement a small immutable registry pinned to the researched source revision/date. Store source URL, pricing basis, model, per-million-token rates, cache rates, and long-context threshold/rates. Normalize qualified model names without guessing unknown model prices.
4. Return a bounded estimate object with `reference_usd`, `copilot_ai_credits`, `price_version`, `pricing_basis`, source URL, and completeness/unknown reason. Treat missing token dimensions as incomplete rather than silently free.
5. Run the focused tests and refactor only after they are green.

**Verification:** `pytest apps/api/tests/test_usage.py -q` passes with the new pricing assertions.

### Task 2: Persist and expose complete usage dimensions and rollups

**Files:**
- Modify: `apps/api/app/usage.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/orchestrator.py`
- Modify: `apps/api/app/execution.py`
- Test: `apps/api/tests/test_usage.py`

**Steps:**
1. Add failing tests for cache fields in worker record/finalize requests, persisted estimate metadata, totals that include processed/cache tokens, model breakdown, daily breakdown, unknown pricing, and project scoping.
2. Run the focused API tests and confirm the failures are about missing fields/rollups.
3. Extend record/finalize paths to carry cache read/write fields and refresh the existing `price_version`/`estimated_cost` columns with the pinned estimate. Keep reported billing nullable and untouched unless a provider actually supplies it.
4. Add backward-compatible `/usage` fields: token totals, processed tokens, estimated reference USD, Copilot AI credits/USD equivalent, completeness, source attribution, model rows, and daily rows. Include cache and estimate fields in `/usage/calls` and control-room usage views.
5. Run focused API tests, then the full API suite.

**Verification:** `pytest apps/api/tests/test_usage.py apps/api/tests/test_execution.py -q` passes; existing unknown-billing tests remain valid except where they now assert the new explicit estimate fields.

### Task 2a: Add live GitHub billing evidence without storing credentials

**Files:**
- Create: `apps/api/app/github_billing.py`
- Modify: `apps/api/app/settings.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_usage.py`

**Steps:**
1. Write failing tests for an unconfigured billing source, a redacted live request, and robust parsing of the official AI-credit usage response.
2. Read the PAT from explicit environment aliases only; never return it, store it in PostgreSQL, or reuse Pi OAuth credentials. Support personal, organization, and enterprise scopes through environment configuration.
3. Call the official GitHub billing endpoint on demand from the Usage page, keeping account-level gross/net/discount/credit totals separate from project-local estimates. Treat subscription plan fees and allowance balances as unavailable unless GitHub returns them.
4. Expose an honest source/status/error payload so the UI can distinguish live reported billing, local reference estimates, and an unconfigured account.

**Verification:** focused API tests prove no token leakage; a live call is attempted only when the configured PAT is present, and an unconfigured local run remains healthy.

### Task 3: Make Usage a useful accounting surface

**Files:**
- Modify: `apps/web/index.html`
- Modify: `apps/web/src/app.js`
- Modify: `apps/web/src/styles.css`
- Modify: `apps/web/tests/view-models.test.mjs`

**Steps:**
1. Add failing view-model tests for token/currency formatting and clear labels distinguishing API-equivalent USD, Copilot AI credits, reported billed cost, and unknowns.
2. Run `npm run verify` in `apps/web` and confirm the new assertions fail.
3. Replace the single Usage paragraph with spaced summary cards, token dimensions, an estimate explanation, model breakdown table, daily activity rows/bars, and enriched call cards while retaining the existing call lineage and quota panel.
4. Keep the UI honest: show `~`/“estimate” labels, the source date/link, “not an invoice,” and “plan allowance/actual subscription bill unavailable” when no provider billing report is available.
5. Run the web tests and inspect the LAN page at desktop and narrow widths.

**Verification:** `npm run verify` in `apps/web` passes; manual browser inspection shows no clipped tables or overlapping summary cards.

### Task 4: Add reusable loading skeletons throughout the dashboard

**Files:**
- Modify: `apps/web/src/app.js`
- Modify: `apps/web/src/styles.css`
- Modify: `apps/web/index.html`

**Steps:**
1. Add a small skeleton renderer with variants for cards, rows, messages, stages, artifacts, and stats; keep it accessible with `aria-busy` and screen-reader status text.
2. Invoke it before every major asynchronous load: projects, catalog, providers, Telegram status, selected-project messages/events/execution/sections/reviews/artifacts, Usage, quota, and protected previews where a placeholder is useful.
3. Ensure every success, empty, and error path clears the skeleton and that stale project responses cannot render into a newly selected project.
4. Run the web tests, `git diff --check`, and manual browser refresh/project-switch checks.

**Verification:** `npm run verify` in `apps/web` passes and a browser refresh shows intentional skeletons rather than blank jumps for each loaded panel.

### Task 5: Document pricing boundaries, Copilot workaround, and ship

**Files:**
- Modify: `docs/INTEGRATIONS.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/STATUS.md`
- Modify: `docs/SCORECARD.md`
- Modify: `docs/AGENT_LEDGER.md`
- Modify: `packages/contracts/generated.ts`
- Modify: `packages/contracts/openapi.json`

**Steps:**
1. Document official price sources, the distinction between API-equivalent estimates and actual subscription billing, and the Copilot runtime-price limitation/workaround.
2. Regenerate contracts if the API schema changes.
3. Run the full repository verification and live service checks.
4. Commit coherent packets, push `codex/ebook-factory-v2`, restart user services if needed, and record the exact evidence and action ledger row.

**Verification:** `make verify`, `git diff --check`, clean worktree, remote branch at the final commit, and `/ready` returns HTTP 200.
