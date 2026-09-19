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
  "run.plan.created": "Production plan created",
  "task.enqueued": "Task queued",
  "job.claimed": "Work started",
  "agent.started": "Agent started",
  "job.checkpointed": "Work checkpointed",
  "job.completed": "Work completed",
  "agent.completed": "Agent completed",
  "job.failed": "Work failed",
  "agent.failed": "Agent failed",
  "job.retry_wait": "Work retrying",
  "job.paused": "Work paused",
  "job.resumed": "Work resumed",
  "job.blocked": "Work blocked",
  "run.cancelled": "Run cancelled",
  "production.output.accepted": "Draft accepted",
  "artifact.owner_reviewed": "Owner reviewed artwork",
  "art.revision.queued": "Artwork revision queued",
  "art.generated": "Artwork generated",
  "review.finding.created": "Review finding recorded",
  "review.finding.resolved": "Review finding resolved",
  "package.preview_reviewed": "Kindle preview recorded",
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

export function formatBriefLength(brief = {}) {
  const pages = brief.target_pages;
  if (pages?.minimum != null && pages?.maximum != null) {
    return `${Number(pages.minimum).toLocaleString()}–${Number(pages.maximum).toLocaleString()} pages`;
  }
  const words = brief.target_length;
  if (words?.minimum_words != null && words?.maximum_words != null) {
    return `${Number(words.minimum_words).toLocaleString()}–${Number(words.maximum_words).toLocaleString()} words`;
  }
  return "Length not set";
}

export function groupArtifact(artifact = {}) {
  const path = String(artifact.relative_path || "").toLowerCase();
  if (path.startsWith("exports/")) return "package";
  if (artifact.mime_type?.startsWith("image/")) return "artwork";
  const extension = artifactFilename(artifact).split(".").pop()?.toLowerCase();
  if (["json", "csv"].includes(extension) || /metadata|manifest|sources|validation/.test(path)) return "metadata";
  return "manuscript";
}

export function executionTaskTree(run = {}) {
  const tasks = (run.tasks || []).map((task) => ({ ...task, children: [] }));
  const byId = new Map(tasks.map((task) => [String(task.task_id), task]));
  const roots = [];
  tasks.forEach((task) => {
    const parent = task.parent_task_id && byId.get(String(task.parent_task_id));
    if (parent) parent.children.push(task);
    else roots.push(task);
  });
  return roots;
}

export function executionEventPresentation(event = {}) {
  const payload = event.payload || {};
  if (event.kind === "artifact.owner_reviewed") {
    const decision = payload.decision === "approve" ? "Approved" : "Revision requested";
    return { label: "Owner reviewed artwork", detail: `${decision}${payload.note ? ` · ${payload.note}` : ""}`, tone: "review" };
  }
  if (event.kind === "agent.started") {
    return { label: "Agent started", detail: payload.task_type ? `Working on ${payload.task_type}.` : "A bounded task attempt started.", tone: "active" };
  }
  if (event.kind === "agent.completed") {
    return { label: "Agent completed", detail: payload.task_type ? `${payload.task_type} returned a durable result.` : "A bounded task completed.", tone: "complete" };
  }
  if (event.kind === "art.revision.queued") {
    return { label: "Artwork revision queued", detail: "Owner feedback is queued for a new immutable image.", tone: "active" };
  }
  if (event.kind === "run.plan.created") {
    return { label: "Production plan created", detail: `${payload.task_count || "The"} durable task${payload.task_count === 1 ? "" : "s"} recorded for this run.`, tone: "active" };
  }
  if (event.kind === "task.enqueued") {
    return { label: "Task queued", detail: payload.task_type ? `${payload.task_type} is waiting for its dependencies.` : "A bounded task is waiting for execution.", tone: "active" };
  }
  if (event.kind === "job.claimed" || event.kind === "orchestrator.turn.claimed") {
    return { label: formatEventKind(event.kind), detail: payload.task_type ? `A worker claimed ${payload.task_type}.` : "A durable worker lease is active.", tone: "active" };
  }
  if (event.kind === "job.completed") {
    return { label: "Work completed", detail: payload.task_type ? `${payload.task_type} completed and recorded its result.` : "A durable job completed.", tone: "complete" };
  }
  if (event.kind === "job.failed" || event.kind === "agent.failed") {
    return { label: formatEventKind(event.kind), detail: payload.error_class ? `Failure boundary: ${payload.error_class}.` : "Inspect the task attempt for the failure boundary.", tone: "review" };
  }
  if (event.kind === "production.output.accepted") {
    return { label: "Draft accepted", detail: "The manuscript revision is now available to inspect.", tone: "complete" };
  }
  if (event.kind === "review.finding.created") {
    return { label: "Review finding recorded", detail: payload.criterion ? `${payload.severity || "Review"} · ${payload.criterion}.` : "A review finding is attached to the source.", tone: "review" };
  }
  if (event.kind === "review.finding.resolved") {
    return { label: "Review finding resolved", detail: "A later source revision was recorded as the resolution.", tone: "complete" };
  }
  if (event.kind === "package.preview_reviewed") {
    const decision = payload.decision === "verified" ? "verified" : "issues found";
    const surface = payload.surface === "kdp_online_previewer" ? "KDP Online Previewer" : "Kindle Previewer";
    const hash = payload.artifact_sha256 ? ` · EPUB ${String(payload.artifact_sha256).slice(0, 12)}…` : "";
    return { label: "Kindle preview recorded", detail: `${surface} · ${decision}${hash}`, tone: payload.decision === "verified" ? "complete" : "review" };
  }
  return { label: formatEventKind(event.kind), detail: "", tone: "neutral" };
}

export function conversationEmptyState(execution = {}) {
  if ((execution.conversation || []).length) return "";
  if ((execution.runs || []).length) return "No owner chat turn was used for this production run. The durable task trace below is the source of truth.";
  return "No conversation yet. Start with the book idea or fill in the brief to begin.";
}

function hasDraft(sections) {
  return sections.some((section) => section.latest_revision_id || section.content?.trim());
}

function sourceImages(artifacts) {
  return artifacts.filter((artifact) => artifact.mime_type?.startsWith("image/") && !String(artifact.relative_path || "").startsWith("exports/"));
}

export function kindlePreviewCheckpoint(artifacts = [], events = []) {
  const epub = artifacts.find((artifact) => {
    const filename = artifactFilename(artifact).toLowerCase();
    return filename === "book.epub" && String(artifact.relative_path || "").startsWith("exports/");
  }) || null;
  if (!epub) return { status: "not_applicable", artifact: null, review: null };
  const review = [...events]
    .reverse()
    .find((event) => event.kind === "package.preview_reviewed" && event.payload?.artifact_sha256 === epub.sha256) || null;
  if (review?.payload?.decision === "verified") return { status: "verified", artifact: epub, review };
  if (review?.payload?.decision === "issues_found") return { status: "issues_found", artifact: epub, review };
  return { status: "pending", artifact: epub, review: null };
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
  const preview = kindlePreviewCheckpoint(artifacts, events);

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
      key: "kindle_preview",
      label: "Kindle preview",
      status: preview.status === "not_applicable"
        ? "not_applicable"
        : preview.status === "verified"
          ? "complete"
          : preview.status === "issues_found"
            ? "needs_review"
            : exportsExist
              ? "current"
              : "waiting",
      detail: preview.status === "not_applicable"
        ? "No EPUB was requested for this package."
        : preview.status === "verified"
          ? "The owner recorded an external visual preview for this exact EPUB."
          : preview.status === "issues_found"
            ? "Preview issues are recorded; rebuild the package after correcting the source."
            : exportsExist
              ? "Open Kindle Previewer or KDP Online Previewer and record the result against this EPUB hash."
              : "External Kindle preview follows an EPUB export.",
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
