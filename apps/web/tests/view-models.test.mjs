import test from "node:test";
import assert from "node:assert/strict";

import {
  artifactAvailabilityLabel,
  artifactIsAvailable,
  artifactPresentation,
  deriveStageStates,
  executionEventPresentation,
  executionTaskTree,
  formatBriefLength,
  groupArtifact,
  conversationEmptyState,
  formatArtifactSize,
  formatEventKind,
  formatUsageCost,
  formatUsageTokens,
  usageBasisLabel,
  usageEstimateLabel,
  usageScopeCopy,
  githubBillingStatusCopy,
  modelCatalogLabel,
  kindlePreviewCheckpoint,
} from "../src/view-models.js";

test("artifact availability keeps legacy package responses usable and flags missing files", () => {
  assert.equal(artifactIsAvailable({ relative_path: "exports/revision/book.epub" }), true);
  assert.equal(artifactIsAvailable({ availability_state: "missing" }), false);
  assert.equal(artifactAvailabilityLabel({ availability_state: "integrity_failed" }), "Integrity failed");
});

test("artifactPresentation turns storage paths into readable file cards", () => {
  assert.deepEqual(
    artifactPresentation({
      relative_path: "exports/revision/book.epub",
      mime_type: "application/epub+zip",
    }),
    {
      filename: "book.epub",
      extension: "EPUB",
      label: "Ebook",
      icon: "EPUB",
      kind: "ebook",
      isImage: false,
      isExport: true,
    },
  );
});

test("artifactPresentation recognizes protected image previews", () => {
  const presentation = artifactPresentation({
    relative_path: "run-id/cover.png",
    mime_type: "image/png",
  });

  assert.equal(presentation.filename, "cover.png");
  assert.equal(presentation.label, "Artwork");
  assert.equal(presentation.icon, "PNG");
  assert.equal(presentation.kind, "image");
  assert.equal(presentation.isImage, true);
  assert.equal(presentation.isExport, false);
});

test("stage states expose the owner checkpoint from durable project data", () => {
  const stages = deriveStageStates(
    { state: "draft_review" },
    {
      sections: [{ latest_revision_id: "revision-1", content: "A draft" }],
      reviews: [],
      artifacts: [
        {
          relative_path: "run-id/cover.png",
          mime_type: "image/png",
          owner_review_state: "pending",
        },
        { relative_path: "exports/revision/book.epub", mime_type: "application/epub+zip" },
      ],
      events: [{ kind: "run.approved" }],
    },
  );

  assert.deepEqual(
    stages.map(({ key, status }) => ({ key, status })),
    [
      { key: "brief", status: "complete" },
      { key: "outline", status: "complete" },
      { key: "draft", status: "complete" },
      { key: "review", status: "needs_review" },
      { key: "art", status: "needs_review" },
      { key: "export", status: "complete" },
      { key: "kindle_preview", status: "current" },
      { key: "owner", status: "needs_review" },
    ],
  );
});

test("stage details include the latest orchestrator gate decision", () => {
  const stages = deriveStageStates(
    { state: "draft_review" },
    { sections: [{ latest_revision_id: "revision-1" }], events: [{ kind: "orchestrator.gate.updated", payload: { gate: "draft", status: "needs_review", note: "Readability pass requested." } }] },
  );

  assert.equal(stages.find((stage) => stage.key === "draft").status, "needs_review");
  assert.match(stages.find((stage) => stage.key === "draft").detail, /^Orchestrator gate: Needs review · Readability pass requested\./);
});

test("format helpers keep the timeline and artifact metadata compact", () => {
  assert.equal(formatArtifactSize(5304), "5.2 KB");
  assert.equal(formatArtifactSize(293427), "286.5 KB");
  assert.equal(formatEventKind("production.output.accepted"), "Draft accepted");
  assert.equal(formatEventKind("job.failed"), "Work failed");
});

test("model catalog labels expose provider pricing in selector-friendly text", () => {
  assert.match(modelCatalogLabel({
    qualified_model: "github-copilot/gpt-5-mini",
    context: "264K",
    max_output: "64K",
    pricing: {
      pricing_basis: "github_ai_credits",
      input_per_million: 0.25,
      cache_read_per_million: 0.025,
      output_per_million: 2,
    },
  }), /25 credits\/M input/);
  assert.match(modelCatalogLabel({
    qualified_model: "openai-codex/gpt-5.6-luna",
    context: "272K",
    max_output: "128K",
    pricing: { pricing_basis: "api_equivalent", input_per_million: 0.2, output_per_million: 1.2 },
  }), /\$0\.20\/M input/);
  assert.match(modelCatalogLabel({
    qualified_model: "openai-codex/gpt-5.3-codex-spark",
    context: "128K",
    max_output: "128K",
    pricing: null,
  }), /pricing unavailable/);
});

test("executionTaskTree preserves parent and dependency relationships", () => {
  const tree = executionTaskTree({ tasks: [
    { task_id: "outline", task_type: "outline", parent_task_id: null, dependencies: [], status: "succeeded", attempts: [] },
    { task_id: "production", task_type: "production", parent_task_id: "outline", dependencies: ["outline"], status: "running", attempts: [] },
  ] });

  assert.equal(tree.length, 1);
  assert.equal(tree[0].task_id, "outline");
  assert.equal(tree[0].children[0].task_id, "production");
  assert.deepEqual(tree[0].children[0].dependencies, ["outline"]);
});

test("execution event presentation explains reviews and agent lifecycle", () => {
  assert.deepEqual(
    executionEventPresentation({ kind: "artifact.owner_reviewed", payload: { decision: "request_revision", note: "Use a stronger scene." } }),
    { label: "Owner reviewed artwork", detail: "Revision requested · Use a stronger scene.", tone: "review" },
  );
  assert.equal(executionEventPresentation({ kind: "agent.started", payload: { task_type: "art-revision" } }).label, "Agent started");
  assert.deepEqual(
    executionEventPresentation({
      kind: "package.preview_reviewed",
      payload: { decision: "verified", surface: "kindle_previewer", artifact_sha256: "a".repeat(64) },
    }),
    { label: "Kindle preview recorded", detail: "Kindle Previewer · verified · EPUB aaaaaaaaaaaa…", tone: "complete" },
  );
  assert.deepEqual(
    executionEventPresentation({
      kind: "orchestrator.tool.completed",
      payload: { tool_name: "factory_read_state" },
    }),
    { label: "Orchestrator tool completed", detail: "factory_read_state returned a project-scoped result.", tone: "complete" },
  );
  assert.deepEqual(
    executionEventPresentation({
      kind: "orchestrator.gate.updated",
      payload: { gate: "draft", status: "needs_review", note: "Owner review is required." },
    }),
    { label: "Draft gate updated", detail: "Needs review · Owner review is required.", tone: "review" },
  );
  assert.deepEqual(
    executionEventPresentation({
      kind: "agent.tool.completed",
      payload: { task_type: "orchestrator-research", tool_name: "factory_read_state" },
    }),
    { label: "Agent tool completed", detail: "orchestrator-research received a tool result.", tone: "complete" },
  );
});

test("kindle preview checkpoint follows the package hash and durable review event", () => {
  const artifact = {
    artifact_id: "epub-1",
    revision_id: "revision-1",
    relative_path: "exports/revision-1/book.epub",
    filename: "book.epub",
    mime_type: "application/epub+zip",
    sha256: "b".repeat(64),
  };
  assert.equal(kindlePreviewCheckpoint([artifact], []).status, "pending");
  assert.equal(
    kindlePreviewCheckpoint([artifact], [{ id: 4, kind: "package.preview_reviewed", payload: { artifact_sha256: artifact.sha256, decision: "verified" } }]).status,
    "verified",
  );
  assert.equal(
    kindlePreviewCheckpoint([artifact], [{ id: 5, kind: "package.preview_reviewed", payload: { artifact_sha256: artifact.sha256, decision: "issues_found" } }]).status,
    "issues_found",
  );
  assert.equal(kindlePreviewCheckpoint([{ relative_path: "exports/revision-1/book.pdf" }], []).status, "not_applicable");
});

test("brief length and artifact grouping keep metadata useful", () => {
  assert.equal(formatBriefLength({ target_pages: { minimum: 50, maximum: 150 } }), "50–150 pages");
  assert.equal(formatBriefLength({ target_length: { minimum_words: 1200, maximum_words: 3000 } }), "1,200–3,000 words");
  assert.equal(groupArtifact({ relative_path: "exports/revision/book.epub", mime_type: "application/epub+zip" }), "package");
  assert.equal(groupArtifact({ relative_path: "run/cover.png", mime_type: "image/png" }), "artwork");
  assert.equal(groupArtifact({ relative_path: "run/metadata.json", mime_type: "application/json" }), "metadata");
  assert.equal(groupArtifact({ relative_path: "run/book.md", mime_type: "text/markdown" }), "manuscript");
});

test("empty conversation tells the owner when approval bypassed chat", () => {
  assert.equal(
    conversationEmptyState({ conversation: [], runs: [{ state: "draft_review" }] }),
    "This run began from the brief; no owner chat turn has been recorded yet. Send a direction here to make decisions visible alongside the durable task trace.",
  );
});

test("usage helpers distinguish token scale, reference estimates, and billing evidence", () => {
  assert.equal(formatUsageTokens(1_234_567), "1.2M");
  assert.equal(formatUsageTokens(null), "—");
  assert.equal(formatUsageCost(12.345), "~$12.35");
  assert.equal(formatUsageCost(null), "Unavailable");
  assert.equal(usageBasisLabel("api_equivalent"), "API-equivalent reference");
  assert.equal(usageBasisLabel("github_ai_credits"), "GitHub AI credits");
  assert.equal(usageEstimateLabel({ estimated_cost: 1.25, reported_billed_cost: null }), "~$1.25 reference estimate");
  assert.equal(usageEstimateLabel({ estimated_cost: null, reported_billed_cost: 1.1 }), "$1.10 reported");
  assert.equal(usageEstimateLabel({ estimated_cost: null, reported_billed_cost: null }), "Billing unavailable");
});

test("usage scope copy keeps workspace totals visible beside the selected project", () => {
  assert.equal(
    usageScopeCopy({ workspaceCalls: 60, projectCalls: 4, projectTitle: "Luna Low Demo Nonfiction" }),
    "60 calls in this workspace · 4 in Luna Low Demo Nonfiction",
  );
  assert.equal(usageScopeCopy({ workspaceCalls: 0 }), "No provider calls recorded in this workspace yet.");
});

test("GitHub billing copy distinguishes an accepted PAT from a missing billing scope", () => {
  assert.match(
    githubBillingStatusCopy({ status: "error", http_status: 404, identity_verified: true, account: { identifier: "owner" } }),
    /PAT authenticated as owner.*no personal billable Copilot record/,
  );
  assert.match(
    githubBillingStatusCopy({ status: "error", http_status: 403, identity_verified: true, account: { identifier: "owner" } }),
    /Plan: read permission/,
  );
});
