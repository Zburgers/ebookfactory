import test from "node:test";
import assert from "node:assert/strict";

import {
  artifactPresentation,
  deriveStageStates,
  executionEventPresentation,
  executionTaskTree,
  formatBriefLength,
  groupArtifact,
  conversationEmptyState,
  formatArtifactSize,
  formatEventKind,
} from "../src/view-models.js";

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
      { key: "owner", status: "needs_review" },
    ],
  );
});

test("format helpers keep the timeline and artifact metadata compact", () => {
  assert.equal(formatArtifactSize(5304), "5.2 KB");
  assert.equal(formatArtifactSize(293427), "286.5 KB");
  assert.equal(formatEventKind("production.output.accepted"), "Draft accepted");
  assert.equal(formatEventKind("job.failed"), "Work failed");
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
    "No owner chat turn was used for this production run. The durable task trace below is the source of truth.",
  );
});
