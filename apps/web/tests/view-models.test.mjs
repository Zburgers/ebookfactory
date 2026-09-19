import test from "node:test";
import assert from "node:assert/strict";

import {
  artifactPresentation,
  deriveStageStates,
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
