const FILE_TYPES = {
  epub: { extension: "EPUB", label: "Ebook", icon: "EPUB", kind: "ebook" },
  pdf: { extension: "PDF", label: "Print PDF", icon: "PDF", kind: "document" },
  docx: { extension: "DOCX", label: "Word document", icon: "DOCX", kind: "document" },
  md: { extension: "MD", label: "Markdown", icon: "MD", kind: "document" },
  jpg: { extension: "JPG", label: "Cover image", icon: "JPG", kind: "image" },
  jpeg: { extension: "JPG", label: "Cover image", icon: "JPG", kind: "image" },
  png: { extension: "PNG", label: "Artwork", icon: "PNG", kind: "image" },
  json: { extension: "JSON", label: "Metadata", icon: "{}", kind: "data" },
  csv: { extension: "CSV", label: "Metadata sheet", icon: "CSV", kind: "data" },
};

const EVENT_LABELS = {
  "project.created": "Project created",
  "conversation.message.received": "Owner message received",
  "orchestrator.turn.queued": "Orchestrator queued",
  "orchestrator.turn.claimed": "Orchestrator started",
  "orchestrator.turn.completed": "Orchestrator replied",
  "orchestrator.turn.failed": "Orchestrator failed",
  "orchestrator.turn.retryable_failure": "Orchestrator retrying",
  "run.approved": "Brief approved",
  "job.claimed": "Work started",
  "job.checkpointed": "Work checkpointed",
  "job.completed": "Work completed",
  "job.failed": "Work failed",
  "job.paused": "Work paused",
  "job.resumed": "Work resumed",
  "job.blocked": "Work blocked",
  "run.cancelled": "Run cancelled",
  "production.output.accepted": "Draft accepted",
};

const TERMINAL_STATES = new Set(["blocked", "failed", "cancelled"]);
const ACTIVE_STATES = new Set(["producing", "draft_review", "art_review", "packaging"]);

export function artifactFilename(artifact) {
  return artifact.filename || String(artifact.relative_path || "").split("/").pop() || "artifact";
}

export function artifactPresentation(artifact) {
  const filename = artifactFilename(artifact);
  const extensionKey = filename.includes(".") ? filename.split(".").pop().toLowerCase() : "";
  const known = FILE_TYPES[extensionKey];
  const isImage = artifact.mime_type?.startsWith("image/") || known?.kind === "image";
  const fallback = {
    extension: extensionKey ? extensionKey.toUpperCase() : "FILE",
    label: artifact.mime_type || "File",
    icon: extensionKey ? extensionKey.toUpperCase().slice(0, 4) : "FILE",
    kind: isImage ? "image" : "file",
  };
  const type = known || fallback;
  return {
    filename,
    extension: type.extension,
    label: type.label,
    icon: type.icon,
    kind: type.kind,
    isImage,
    isExport: String(artifact.relative_path || "").startsWith("exports/"),
  };
}

export function formatArtifactSize(bytes) {
  const value = Number(bytes) || 0;
  if (value < 1024) return `${value} B`;
  const units = ["KB", "MB", "GB"];
  let scaled = value;
  let unit = units[0];
  for (const candidate of units) {
    scaled /= 1024;
    unit = candidate;
    if (scaled < 1024 || candidate === units.at(-1)) break;
  }
  return `${scaled.toFixed(1)} ${unit}`;
}

export function formatEventKind(kind) {
  return EVENT_LABELS[kind] || String(kind || "Event").replaceAll(".", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function hasDraft(sections) {
  return sections.some((section) => section.latest_revision_id || section.content?.trim());
}

function sourceImages(artifacts) {
  return artifacts.filter((artifact) => artifact.mime_type?.startsWith("image/") && !String(artifact.relative_path || "").startsWith("exports/"));
}

export function deriveStageStates(project, { sections = [], reviews = [], artifacts = [], events = [] } = {}) {
  const state = project?.state || "brainstorming";
  const terminal = TERMINAL_STATES.has(state);
  const active = ACTIVE_STATES.has(state);
  const approvedBrief = events.some((event) => event.kind === "run.approved") || !["brainstorming", "brief_ready"].includes(state);
  const draftExists = hasDraft(sections);
  const images = sourceImages(artifacts);
  const pendingImages = images.some((artifact) => artifact.owner_review_state !== "approved");
  const exportsExist = artifacts.some((artifact) => String(artifact.relative_path || "").startsWith("exports/"));
  const openFindings = reviews.some((finding) => !finding.resolution_revision_id);

  const stages = [
    {
      key: "brief",
      label: "Brief",
      status: approvedBrief ? "complete" : state === "brainstorming" ? "current" : "waiting",
      detail: approvedBrief ? "Approved brief is driving this run." : "Shape and approve the exact brief.",
    },
    {
      key: "outline",
      label: "Outline",
      status: sections.length ? "complete" : active ? "current" : "waiting",
      detail: sections.length ? `${sections.length} section${sections.length === 1 ? "" : "s"} recorded.` : "Waiting for the approved brief.",
    },
    {
      key: "draft",
      label: "Draft",
      status: draftExists ? "complete" : state === "producing" ? "current" : "waiting",
      detail: draftExists ? "A readable manuscript revision is available." : "The manuscript has not been accepted yet.",
    },
    {
      key: "review",
      label: "Review",
      status: state === "draft_review" || openFindings ? "needs_review" : ["art_review", "packaging", "package_ready"].includes(state) ? "complete" : "waiting",
      detail: state === "draft_review" || openFindings ? "Draft is ready for owner review." : "Review follows the accepted draft.",
    },
    {
      key: "art",
      label: "Artwork",
      status: pendingImages ? "needs_review" : images.length ? "complete" : state === "art_review" ? "current" : "waiting",
      detail: pendingImages ? "Artwork is ready for an owner decision." : images.length ? "Source artwork has been reviewed." : "No source artwork is recorded yet.",
    },
    {
      key: "export",
      label: "Export",
      status: exportsExist ? "complete" : state === "packaging" ? "current" : "waiting",
      detail: exportsExist ? "Validated package artifacts are available." : "Package generation follows review and art.",
    },
    {
      key: "owner",
      label: "Owner sign-off",
      status: pendingImages || exportsExist ? "needs_review" : "waiting",
      detail: pendingImages ? "Review the artwork before approving the package." : exportsExist ? "Package is ready for your final inspection." : "The owner checkpoint comes after export.",
    },
  ];

  if (terminal) {
    stages.forEach((stage) => {
      if (stage.status === "current" || stage.status === "waiting") {
        stage.status = "blocked";
        stage.detail = `Run is ${state}; inspect the event history for the failure boundary.`;
      }
    });
  }
  return stages;
}
