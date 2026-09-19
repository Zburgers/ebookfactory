import { fetchProtectedArtifact } from "./artifact-client.js";
import { artifactFilename, artifactPresentation, conversationEmptyState, deriveStageStates, executionEventPresentation, executionTaskTree, formatArtifactSize, formatBriefLength, groupArtifact, kindlePreviewCheckpoint } from "./view-models.js";

const state = { projects: [], selected: null, sections: [], reviews: [], artifacts: [], events: [], messages: [], execution: null, packageResult: null, providers: [], catalog: null, eventCursor: 0, streamController: null, liveAssistant: null, replayingEvents: false, artifactUrls: [] };
const $ = (selector) => document.querySelector(selector);
const ownerToken = () => sessionStorage.getItem("ebook-factory-owner-token") || "";
const applyTheme = (theme) => { document.documentElement.dataset.theme = theme; $("#theme-label").textContent = theme === "dark" ? "Light surface" : "Night surface"; $("#theme-icon").textContent = theme === "dark" ? "○" : "●"; localStorage.setItem("ebook-factory-theme", theme); };
applyTheme(localStorage.getItem("ebook-factory-theme") || "dark");
$("#theme-toggle").addEventListener("click", () => applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
const api = async (path, options = {}) => { const headers = { "content-type": "application/json", ...(options.headers || {}) }; const token = ownerToken(); if (token) headers.Authorization = `Bearer ${token}`; const response = await fetch(path, { ...options, headers }); if (!response.ok) { const error = new Error((await response.text()).slice(0, 240)); error.status = response.status; throw error; } return response.status === 204 ? null : response.json(); };
const showError = (id, error) => { $(id).textContent = error.message || String(error); };
function addSavedOption(select, value, label) { if (!value) return; const option = [...select.options].find((candidate) => candidate.value === value); if (option) { option.selected = true; return; } const saved = document.createElement("option"); saved.value = value; saved.textContent = label + " (saved; unavailable)"; saved.selected = true; select.append(saved); }
function populateCatalogSelects(saved = {}) { const models = state.catalog?.models || []; const providerSelect = $("#provider-select"); const modelSelects = [$("#orchestration-model"), $("#drafting-model"), $("#review-model")]; providerSelect.replaceChildren(); [...new Set(models.map((model) => model.provider))].sort().forEach((provider) => { const option = document.createElement("option"); option.value = provider; option.textContent = provider; providerSelect.append(option); }); addSavedOption(providerSelect, saved.provider, "Provider"); modelSelects.forEach((select) => { select.replaceChildren(); models.forEach((model) => { const option = document.createElement("option"); option.value = model.qualified_model; option.textContent = model.qualified_model + " · context " + model.context + " · max " + model.max_output; select.append(option); }); }); addSavedOption($("#orchestration-model"), saved.orchestration_model, "Main orchestrator model"); addSavedOption($("#drafting-model"), saved.drafting_model, "Drafting model"); addSavedOption($("#review-model"), saved.review_model, "Review model"); }
function currentCatalogSelections() { return { provider: $("#provider-select").value, orchestration_model: $("#orchestration-model").value, drafting_model: $("#drafting-model").value, review_model: $("#review-model").value }; }
function filterCatalogModels(provider) { const models = (state.catalog?.models || []).filter((model) => model.provider === provider); const labels = ["Main orchestrator model", "Drafting model", "Review model"]; [$("#orchestration-model"), $("#drafting-model"), $("#review-model")].forEach((select, index) => { const selected = select.value; const known = state.catalog?.models.find((model) => model.qualified_model === selected); const staleQualified = !known && selected.includes("/") && selected.split("/", 1)[0] !== provider; select.replaceChildren(); models.forEach((model) => { const option = document.createElement("option"); option.value = model.qualified_model; option.textContent = model.qualified_model + " · context " + model.context + " · max " + model.max_output; select.append(option); }); if (!staleQualified && (!known || known.provider === provider)) addSavedOption(select, selected, labels[index]); if (!select.value && select.options.length) select.selectedIndex = 0; }); }
function bindCatalogCoherence() { $("#provider-select").addEventListener("change", () => filterCatalogModels($("#provider-select").value)); [$("#orchestration-model"), $("#drafting-model"), $("#review-model")].forEach((select) => select.addEventListener("change", () => { const selected = state.catalog?.models.find((model) => model.qualified_model === select.value); if (selected) { $("#provider-select").value = selected.provider; filterCatalogModels(selected.provider); select.value = selected.qualified_model; } })); }
async function loadCatalog() { const status = $("#catalog-status"); const selections = currentCatalogSelections(); try { state.catalog = await api("/providers/catalog"); status.textContent = state.catalog.models.length + " installed Pi models · source: " + state.catalog.source + " · fetched " + new Date(state.catalog.fetched_at).toLocaleString(); populateCatalogSelects(selections); if (selections.provider) filterCatalogModels(selections.provider); } catch (error) { state.catalog = null; status.textContent = "Pi model catalog unavailable: " + error.message; populateCatalogSelects(selections); } }

function renderProjects() { const list = $("#project-list"); list.replaceChildren(); if (!state.projects.length) { const empty = document.createElement("p"); empty.className = "muted"; empty.textContent = "No projects yet. Start with a small idea."; list.append(empty); return; } state.projects.forEach((project) => { const card = document.createElement("button"); card.className = "project-card"; card.innerHTML = `<h3></h3><p class="muted"></p><span class="status-pill"></span>`; card.querySelector("h3").textContent = project.title; card.querySelector("p").textContent = `${project.profile} · ${project.language}`; card.querySelector("span").textContent = project.state; card.addEventListener("click", () => selectProject(project)); list.append(card); }); }
async function loadProjects() { state.projects = await api("/projects"); renderProjects(); }
async function selectProject(project) {
  state.streamController?.abort();
  state.selected = project;
  state.liveAssistant = null;
  state.eventCursor = 0;
  state.events = [];
  state.messages = [];
  state.execution = null;
  state.packageResult = null;
  state.reviews = [];
  state.artifacts = [];
  $("#studio-project-label").textContent = `${project.title} · ${project.state}`;
  document.querySelector('[data-view="studio"]').click();
  renderStageBoard();
  await Promise.all([loadMessages(), loadEvents(), loadExecution(), loadSections(), loadReviews(), loadArtifacts(), loadUsage()]);
  renderBookOverview();
  renderExecutionTree();
  renderMessages();
  startEventStream();
}

function renderMessages() {
  const box = $("#messages");
  box.replaceChildren();
  if (!state.messages.length) {
    const empty = document.createElement("p");
    empty.className = "muted conversation-empty";
    empty.textContent = conversationEmptyState(state.execution || { conversation: [], runs: [] });
    box.append(empty);
    return;
  }
  state.messages.forEach((message) => {
    const item = document.createElement("div");
    item.className = `message ${message.role}`;
    item.textContent = message.content;
    box.append(item);
  });
}

async function loadMessages() {
  if (!state.selected) return;
  state.messages = await api(`/projects/${state.selected.project_id}/messages`);
  renderMessages();
  renderConversationNote();
}

function renderConversationNote() {
  const note = $("#conversation-note");
  if (!note) return;
  note.textContent = state.messages.length
    ? "This is the durable owner/orchestrator conversation. Production work and delegated agents are shown in the control room below."
    : conversationEmptyState(state.execution || { conversation: [], runs: [] });
}

function briefValue(brief, key, fallback = "") {
  const value = brief?.[key];
  return value == null ? fallback : String(value);
}

function setFormValue(selector, value) {
  const control = $(selector);
  if (control && value != null) control.value = value;
}

function hydrateBriefForm() {
  const form = $("#brief-form");
  const brief = state.execution?.brief || {};
  if (!form || form.dataset.dirty === "true") return;
  setFormValue("#brief-title", briefValue(brief, "title", state.selected?.title || ""));
  setFormValue("#brief-genre", briefValue(brief, "genre", state.selected?.profile || ""));
  setFormValue("#brief-author", briefValue(brief, "author"));
  setFormValue("#brief-language", briefValue(brief, "language", state.selected?.language || "en"));
  setFormValue("#brief-promise", briefValue(brief, "promise_or_premise"));
  setFormValue("#brief-description", briefValue(brief, "description"));
  setFormValue("#brief-audience", briefValue(brief, "audience", "General readers"));
  setFormValue("#brief-keywords", Array.isArray(brief.keywords) ? brief.keywords.join(", ") : briefValue(brief, "keywords"));
  setFormValue("#brief-art-direction", briefValue(brief, "art_direction"));
  const pageTarget = brief.target_pages || { minimum: 50, maximum: 150 };
  const wordTarget = brief.target_length || { minimum_words: 1000, maximum_words: 3000 };
  setFormValue("#minimum-pages", pageTarget.minimum);
  setFormValue("#maximum-pages", pageTarget.maximum);
  setFormValue("#minimum-words", wordTarget.minimum_words);
  setFormValue("#maximum-words", wordTarget.maximum_words);
  const mode = brief.target_length ? "words" : "pages";
  document.querySelectorAll("#brief-form [name=length_mode]").forEach((radio) => { radio.checked = radio.value === mode; });
  $("#page-target-fields").classList.toggle("hidden", mode !== "pages");
  $("#word-target-fields").classList.toggle("hidden", mode !== "words");
  const formats = new Set(Array.isArray(brief.output_formats) ? brief.output_formats : ["epub", "pdf", "docx", "markdown"]);
  document.querySelectorAll("#brief-form [name=output_formats]").forEach((checkbox) => { checkbox.checked = formats.has(checkbox.value); });
}

function renderBookOverview() {
  if (!state.selected) return;
  const project = state.execution?.project || state.selected;
  const brief = state.execution?.brief || {};
  const stages = deriveStageStates(project, { sections: state.sections, reviews: state.reviews, artifacts: state.artifacts, events: state.events });
  const focus = stages.find((stage) => ["needs_review", "current", "blocked"].includes(stage.status)) || stages.at(-1);
  $("#overview-state").textContent = project.state || "Unknown";
  $("#overview-title").textContent = briefValue(brief, "title", project.title || "Untitled book");
  $("#overview-description").textContent = briefValue(brief, "description", briefValue(brief, "promise_or_premise", "No description has been saved yet."));
  $("#overview-genre").textContent = [project.profile, briefValue(brief, "genre")].filter(Boolean).join(" · ") || "Not set";
  $("#overview-audience").textContent = briefValue(brief, "audience", "Not set");
  $("#overview-length").textContent = formatBriefLength(brief);
  $("#overview-formats").textContent = Array.isArray(brief.output_formats) && brief.output_formats.length ? brief.output_formats.join(" · ").toUpperCase() : "Not set";
  $("#overview-hash").textContent = brief.content_hash ? `${brief.content_hash.slice(0, 12)}…` : "Not saved";
  $("#overview-next").textContent = focus ? `${focus.label}: ${stageStatusLabel(focus.status)}` : "Start with a brief";
  $("#studio-project-label").textContent = `${project.title} · ${project.state}`;
  hydrateBriefForm();
  renderConversationNote();
}

async function loadExecution() {
  if (!state.selected) return;
  const projectId = state.selected.project_id;
  state.execution = await api(`/projects/${projectId}/execution?limit=500`);
  if (state.selected?.project_id !== projectId) return;
  state.selected = { ...state.selected, ...(state.execution.project || {}) };
  renderBookOverview();
  renderExecutionTree();
  renderMessages();
}

function taskStateLabel(status) {
  return String(status || "unknown").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function renderTaskNode(task, container, depth = 0) {
  const details = document.createElement("details");
  details.className = `execution-task execution-task-${task.status || "unknown"}`;
  details.open = depth === 0;
  const summary = document.createElement("summary");
  const title = document.createElement("strong");
  title.textContent = task.task_type || "Task";
  const stateLabel = document.createElement("span");
  stateLabel.className = "task-status";
  stateLabel.textContent = taskStateLabel(task.status);
  summary.append(title, stateLabel);
  details.append(summary);
  const meta = document.createElement("p");
  meta.className = "muted execution-task-meta";
  const provider = task.provider && task.model ? `${task.provider} · ${task.model}` : "Provider/model assigned at execution";
  meta.textContent = `${provider} · ${task.attempts?.length || 0} attempt${task.attempts?.length === 1 ? "" : "s"}`;
  details.append(meta);
  const refs = task.result_refs && Object.keys(task.result_refs).length ? document.createElement("details") : null;
  if (refs) {
    const refsSummary = document.createElement("summary");
    refsSummary.textContent = "Recorded outputs";
    const refsValue = document.createElement("pre");
    refsValue.textContent = JSON.stringify(task.result_refs, null, 2);
    refs.append(refsSummary, refsValue);
    details.append(refs);
  }
  const attempts = task.attempts || [];
  attempts.forEach((attempt) => {
    const attemptLine = document.createElement("p");
    attemptLine.className = "execution-attempt";
    attemptLine.textContent = `Attempt ${attempt.attempt_no}: ${taskStateLabel(attempt.status)}${attempt.worker_id ? ` · ${attempt.worker_id}` : ""}${attempt.error_class ? ` · ${attempt.error_class}` : ""}`;
    details.append(attemptLine);
  });
  if (task.children?.length) {
    const children = document.createElement("div");
    children.className = "execution-children";
    task.children.forEach((child) => renderTaskNode(child, children, depth + 1));
    details.append(children);
  }
  container.append(details);
}

function renderExecutionTree() {
  const box = $("#execution-tree");
  if (!box) return;
  box.replaceChildren();
  const runs = state.execution?.runs || [];
  if (!runs.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "No approved production run yet. Save and approve a brief to create the durable plan.";
    box.append(empty);
    return;
  }
  runs.forEach((run, index) => {
    const section = document.createElement("section");
    section.className = "execution-run";
    const heading = document.createElement("div");
    heading.className = "execution-run-heading";
    const title = document.createElement("strong");
    title.textContent = `Run ${String(run.plan_revision || index + 1).padStart(2, "0")}`;
    const stateLabel = document.createElement("span");
    stateLabel.className = "task-status";
    stateLabel.textContent = taskStateLabel(run.state);
    heading.append(title, stateLabel);
    section.append(heading);
    const roots = executionTaskTree(run);
    if (!roots.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "The run exists, but no delegated task has been recorded yet.";
      section.append(empty);
    } else {
      roots.forEach((task) => renderTaskNode(task, section));
    }
    box.append(section);
  });
}
function stageStatusLabel(status) { return ({ complete: "Complete", current: "In progress", needs_review: "Needs review", waiting: "Waiting", blocked: "Blocked", not_applicable: "Not applicable" })[status] || status; }
function renderStageBoard() {
  const rail = $("#stage-rail");
  const summary = $("#stage-summary");
  if (!rail || !summary) return;
  rail.replaceChildren();
  if (!state.selected) { summary.textContent = "Select a project to see its current checkpoint."; return; }
  const stages = deriveStageStates(state.selected, { sections: state.sections, reviews: state.reviews, artifacts: state.artifacts, events: state.events });
  stages.forEach((stage, index) => {
    const item = document.createElement("li"); item.className = `stage-card stage-${stage.status}`;
    const marker = document.createElement("span"); marker.className = "stage-marker"; marker.textContent = stage.status === "complete" ? "✓" : String(index + 1).padStart(2, "0"); marker.setAttribute("aria-hidden", "true");
    const content = document.createElement("div"); content.className = "stage-content";
    const heading = document.createElement("div"); heading.className = "stage-heading";
    const title = document.createElement("h3"); title.textContent = stage.label;
    const status = document.createElement("span"); status.className = "stage-status"; status.textContent = stageStatusLabel(stage.status);
    const description = document.createElement("p"); description.className = "muted"; description.textContent = stage.detail;
    heading.append(title, status); content.append(heading, description); item.append(marker, content); rail.append(item);
  });
  const focus = stages.find((stage) => ["needs_review", "current", "blocked"].includes(stage.status)) || stages.at(-1);
  summary.textContent = `${focus.label}: ${stageStatusLabel(focus.status)} · ${focus.detail} Project state: ${state.selected.state}.`;
}
function appendTimelineEvent(event) {
  const list = $("#events");
  list.querySelector(".timeline-empty")?.remove();
  const payload = event.payload || {};
  if (event.kind === "orchestrator.turn.delta" && payload.delta) {
    const previous = list.lastElementChild;
    if (previous?.dataset.turnId === String(payload.turn_id || "")) {
      previous.querySelector(".timeline-detail").textContent += payload.delta;
      previous.querySelector(".timeline-meta").textContent = new Date(event.timestamp).toLocaleString();
      return;
    }
    const item = document.createElement("li");
    item.className = "timeline-active";
    item.dataset.kind = event.kind;
    item.dataset.turnId = String(payload.turn_id || "");
    const heading = document.createElement("strong"); heading.textContent = "Orchestrator response";
    const detail = document.createElement("p"); detail.className = "timeline-detail"; detail.textContent = payload.delta;
    const meta = document.createElement("span"); meta.className = "timeline-meta"; meta.textContent = new Date(event.timestamp).toLocaleString();
    item.append(heading, detail, meta); list.append(item);
    return;
  }
  const presentation = executionEventPresentation(event);
  const item = document.createElement("li"); item.className = `timeline-${presentation.tone || "neutral"}`; item.dataset.kind = event.kind;
  const heading = document.createElement("strong"); heading.textContent = presentation.label;
  const detail = document.createElement("p"); detail.className = "timeline-detail"; detail.textContent = presentation.detail || "Durable event recorded.";
  const meta = document.createElement("span"); meta.className = "timeline-meta"; meta.textContent = new Date(event.timestamp).toLocaleString();
  item.append(heading, detail, meta); list.append(item);
}
function renderTimelineEmpty() {
  const list = $("#events");
  if (list.children.length) return;
  const empty = document.createElement("li"); empty.className = "timeline-empty"; empty.textContent = state.events.length ? "The trace is caught up; new durable activity will appear here." : "No durable activity yet. Save and approve a brief or send an owner message to begin."; list.append(empty);
}
function applyEvent(event) {
  if (!state.selected || event.project_id !== state.selected.project_id || event.id <= state.eventCursor) return;
  state.events.push(event); state.eventCursor = event.id; appendTimelineEvent(event); renderStageBoard(); renderPackageCheckpoint();
  const payload = event.payload || {};
  if (event.kind === "orchestrator.turn.delta" && payload.delta) { if (!state.liveAssistant || state.liveAssistant.turnId !== payload.turn_id) { const element = document.createElement("div"); element.className = "message assistant streaming"; element.setAttribute("aria-live", "polite"); $("#messages").append(element); state.liveAssistant = { turnId: payload.turn_id, text: "", element }; } state.liveAssistant.text += payload.delta; state.liveAssistant.element.textContent = state.liveAssistant.text; }
  if (["orchestrator.turn.completed", "orchestrator.turn.failed"].includes(event.kind)) { state.liveAssistant = null; loadMessages().catch(() => {}); }
  if (!state.replayingEvents && event.kind !== "orchestrator.turn.delta") {
    loadExecution().catch(() => {});
    if (event.kind.startsWith("art.") || event.kind === "artifact.owner_reviewed") loadArtifacts().catch(() => {});
  }
}
async function loadEvents() {
  if (!state.selected) return;
  const restartStream = Boolean(state.streamController && !state.streamController.signal.aborted);
  state.streamController?.abort(); state.streamController = null;
  const list = $("#events"); list.replaceChildren(); state.events = []; state.eventCursor = 0; state.replayingEvents = true;
  let events = [];
  do { events = await api(`/projects/${state.selected.project_id}/events?after=${state.eventCursor}&limit=100`); events.forEach(applyEvent); } while (events.length === 100);
  state.replayingEvents = false; renderTimelineEmpty(); renderStageBoard(); renderBookOverview(); renderPackageCheckpoint(); if (restartStream) startEventStream();
}
function parseSseBlock(block) { const data = block.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trim()).join("\n"); return data ? JSON.parse(data) : null; }
async function startEventStream() { const projectId = state.selected?.project_id; if (!projectId) return; const controller = new AbortController(); state.streamController = controller; while (!controller.signal.aborted && state.selected?.project_id === projectId) { try { const response = await fetch(`/projects/${projectId}/events/stream?after=${state.eventCursor}&follow=true`, { headers: { Authorization: `Bearer ${ownerToken()}` }, signal: controller.signal }); if (!response.ok) throw new Error(`event stream ${response.status}`); const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ""; while (!controller.signal.aborted) { const { done, value } = await reader.read(); if (done) break; buffer += decoder.decode(value, { stream: true }); const blocks = buffer.split("\n\n"); buffer = blocks.pop() || ""; blocks.forEach((block) => { try { const event = parseSseBlock(block); if (event) applyEvent(event); } catch { /* reconnect from the durable cursor */ } }); } } catch (error) { if (controller.signal.aborted) break; await new Promise((resolve) => setTimeout(resolve, 1000)); } } }
async function loadSections() {
  if (!state.selected) return;
  state.sections = await api(`/projects/${state.selected.project_id}/sections`);
  updateExportAction();
  const list = $("#sections"); list.replaceChildren();
  if (!state.sections.length) { const empty = document.createElement("p"); empty.className = "muted"; empty.textContent = "No accepted sections yet."; list.append(empty); renderStageBoard(); return; }
  state.sections.forEach((section) => {
    const card = document.createElement("article"); card.className = "section-card";
    const heading = document.createElement("h4"); heading.textContent = `${section.order_no}. ${section.heading}`; card.append(heading);
    const editor = document.createElement("textarea"); editor.rows = 8; editor.setAttribute("aria-label", `Edit ${section.heading}`); editor.value = section.content || ""; card.append(editor);
    const actions = document.createElement("div"); actions.className = "form-actions";
    const save = document.createElement("button"); save.className = "primary"; save.textContent = "Save revision"; save.disabled = !section.latest_revision_id;
    const exportButton = document.createElement("button"); exportButton.className = "quiet"; exportButton.textContent = "Export package"; exportButton.disabled = !section.latest_revision_id;
    const result = document.createElement("p"); result.className = "muted"; result.setAttribute("aria-live", "polite");
    save.addEventListener("click", async () => { try { const revision = await api(`/sections/${section.section_id}/revisions`, { method: "POST", body: JSON.stringify({ content: editor.value, summary: "Owner revision", expected_parent_revision_id: section.latest_revision_id }) }); result.textContent = `Saved revision ${revision.revision}.`; await loadSections(); await loadEvents(); } catch (error) { result.textContent = error.message; } });
    exportButton.addEventListener("click", async () => { try { const packageResult = await api(`/projects/${state.selected.project_id}/exports/${section.latest_revision_id}`, { method: "POST", body: "{}" }); renderExports(packageResult); result.textContent = `${packageResult.package_state}; Kindle preview remains pending.`; } catch (error) { result.textContent = error.message; } });
    actions.append(save, exportButton); card.append(actions, result); list.append(card);
  });
  renderStageBoard();
}
function currentExportRevision() {
  return state.sections.find((section) => section.latest_revision_id)?.latest_revision_id || null;
}
function updateExportAction() {
  const button = $("#export-current");
  if (!button) return;
  const revisionId = currentExportRevision();
  button.disabled = !revisionId;
  button.title = revisionId ? "Build from the latest persisted manuscript revision" : "A persisted manuscript revision is required";
}
async function buildCurrentPackage() {
  const revisionId = currentExportRevision();
  const status = $("#export-current-result");
  const button = $("#export-current");
  if (!state.selected || !revisionId) { status.textContent = "Accept a manuscript revision before building a package."; return; }
  button.disabled = true; status.textContent = "Validating the frozen source and building EPUB, PDF, DOCX, and Markdown…";
  try {
    const packageResult = await api(`/projects/${state.selected.project_id}/exports/${revisionId}`, { method: "POST", body: "{}" });
    renderExports(packageResult);
    status.textContent = `Package ${packageResult.package_state}. Inspect the Delivery package shelf below.`;
    await Promise.all([loadArtifacts(), loadEvents(), loadExecution()]);
  } catch (error) { status.textContent = `Package build failed: ${error.message}`; }
  finally { updateExportAction(); }
}
function revokeArtifactUrls() { state.artifactUrls.splice(0).forEach((url) => URL.revokeObjectURL(url)); }
async function responseFailure(response) { const detail = (await response.text()).trim(); return detail ? `${response.status}: ${detail.slice(0, 180)}` : `HTTP ${response.status}`; }
async function downloadArtifact(path, filename, button, result) {
  button.disabled = true; button.textContent = "Preparing…"; result.textContent = "Fetching the protected artifact…";
  try {
    const response = await fetchProtectedArtifact(path, { token: ownerToken() });
    if (!response.ok) throw new Error(await responseFailure(response));
    const url = URL.createObjectURL(await response.blob()); state.artifactUrls.push(url);
    const link = document.createElement("a"); link.href = url; link.download = filename; link.hidden = true; document.body.append(link); link.click(); link.remove();
    button.textContent = "Downloaded"; result.textContent = `${filename} is ready in your downloads.`;
    window.setTimeout(() => { URL.revokeObjectURL(url); state.artifactUrls = state.artifactUrls.filter((candidate) => candidate !== url); }, 60_000);
  } catch (error) { button.textContent = "Try again"; result.textContent = `Download failed: ${error.message}`; }
  finally { button.disabled = false; }
}
async function loadProtectedPreview(image, path, filename) {
  try {
    const response = await fetchProtectedArtifact(path, { token: ownerToken() });
    if (!response.ok) throw new Error(await responseFailure(response));
    const url = URL.createObjectURL(await response.blob()); state.artifactUrls.push(url); image.src = url; image.alt = `${filename} preview`;
  } catch { const fallback = document.createElement("p"); fallback.className = "artifact-preview-fallback"; fallback.textContent = "Preview unavailable; download the protected file to inspect it."; image.replaceWith(fallback); }
}
function appendArtifactDetails(item, artifact, presentation) {
  const details = document.createElement("details"); details.className = "artifact-details";
  const summary = document.createElement("summary"); summary.textContent = "File details"; details.append(summary);
  const path = document.createElement("p"); path.className = "muted"; path.textContent = `${artifact.relative_path || presentation.filename} · ${artifact.mime_type || presentation.label}`; details.append(path);
  if (presentation.isImage && (artifact.generation_provider || artifact.generation_model || artifact.usage_call_id)) {
    const provenance = document.createElement("p");
    provenance.className = "artifact-provenance";
    const provider = [artifact.generation_provider, artifact.generation_model].filter(Boolean).join(" · ") || "Provider not reported";
    provenance.textContent = `Generated by ${provider} · usage ${artifact.usage_outcome || "not reported"}${artifact.usage_call_id ? ` · call ${String(artifact.usage_call_id).slice(0, 12)}…` : ""}`;
    details.append(provenance);
  }
  if (artifact.sha256) { const hash = document.createElement("code"); hash.textContent = `SHA-256 ${artifact.sha256}`; details.append(hash); }
  item.append(details);
}
function createArtifactTile(artifact) {
  const presentation = artifactPresentation(artifact);
  const item = document.createElement("article"); item.className = `artifact-tile artifact-${presentation.kind}`;
  const top = document.createElement("div"); top.className = "artifact-tile-top";
  const icon = document.createElement("span"); icon.className = "artifact-icon"; icon.textContent = presentation.icon; icon.setAttribute("aria-hidden", "true");
  const stateLabel = document.createElement("span"); stateLabel.className = "artifact-state"; stateLabel.textContent = artifact.owner_review_state ? reviewStateLabel(artifact.owner_review_state) : artifact.validation_state === "generated" ? "Generated" : "Package member";
  top.append(icon, stateLabel);
  const heading = document.createElement("h4"); heading.textContent = presentation.label;
  const filename = document.createElement("p"); filename.className = "artifact-filename"; filename.textContent = presentation.filename;
  const meta = document.createElement("p"); meta.className = "muted artifact-meta"; meta.textContent = `${artifact.mime_type || presentation.extension} · ${formatArtifactSize(artifact.byte_count)}`;
  const actions = document.createElement("div"); actions.className = "artifact-actions";
  const button = document.createElement("button"); button.type = "button"; button.className = "quiet artifact-download"; button.textContent = "Download";
  const result = document.createElement("p"); result.className = "muted artifact-download-result"; result.setAttribute("role", "status"); result.setAttribute("aria-live", "polite");
  button.addEventListener("click", () => downloadArtifact(artifact.download_path, artifactFilename(artifact), button, result)); actions.append(button, result);
  item.append(top, heading, filename, meta, actions);
  if (presentation.isImage && artifact.download_path) { const preview = document.createElement("div"); preview.className = "artifact-preview-frame"; const image = document.createElement("img"); image.className = "artifact-preview"; image.alt = `${presentation.filename} preview`; image.loading = "lazy"; preview.append(image); item.append(preview); loadProtectedPreview(image, artifact.download_path, presentation.filename); }
  if (artifact.relative_path || artifact.sha256) appendArtifactDetails(item, artifact, presentation);
  const isReviewableImage = presentation.isImage && !presentation.isExport && artifact.artifact_id;
  if (isReviewableImage) appendArtifactReview(item, artifact);
  return item;
}
function packageArtifactMime(filename) {
  return ({ epub: "application/epub+zip", pdf: "application/pdf", docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", md: "text/markdown" })[String(filename).split(".").pop().toLowerCase()] || "application/octet-stream";
}
function normalizedPackageArtifacts(packageResult) {
  return (packageResult?.artifacts || []).map((artifact) => ({
    ...artifact,
    filename: artifact.filename || artifactFilename(artifact),
    revision_id: artifact.revision_id || packageResult.revision_id,
    relative_path: artifact.relative_path || `exports/${packageResult.revision_id}/${artifact.filename}`,
    mime_type: artifact.mime_type || packageArtifactMime(artifact.filename),
  }));
}
function previewField(labelText, control) {
  const label = document.createElement("label"); label.textContent = labelText; label.append(control); return label;
}
function createPreviewReviewForm(epubArtifact, revisionId, checkpoint) {
  const form = document.createElement("form"); form.className = "preview-review-form";
  const surface = document.createElement("select");
  [["kindle_previewer", "Kindle Previewer (desktop)"], ["kdp_online_previewer", "KDP Online Previewer"]].forEach(([value, label]) => { const option = document.createElement("option"); option.value = value; option.textContent = label; surface.append(option); });
  surface.value = checkpoint.review?.payload?.surface || "kindle_previewer";
  const version = document.createElement("input"); version.type = "text"; version.required = true; version.maxLength = 128; version.placeholder = "e.g. Kindle Previewer 3"; version.value = checkpoint.review?.payload?.tool_version || "";
  const notes = document.createElement("textarea"); notes.rows = 3; notes.maxLength = 4000; notes.placeholder = "Record device, orientation, and any visible issue (required for issues found)."; notes.value = checkpoint.review?.payload?.notes || "";
  const actions = document.createElement("div"); actions.className = "form-actions preview-review-actions";
  const verified = document.createElement("button"); verified.type = "submit"; verified.className = "primary"; verified.textContent = "Record verified preview";
  const issues = document.createElement("button"); issues.type = "button"; issues.className = "quiet"; issues.textContent = "Record issues found";
  const status = document.createElement("p"); status.className = "muted preview-review-status"; status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
  const submit = async (decision) => {
    if (!version.value.trim() || (decision === "issues_found" && !notes.value.trim())) { status.textContent = decision === "issues_found" ? "Add notes describing the preview issue before saving." : "Enter the preview tool/version before saving."; return; }
    actions.querySelectorAll("button").forEach((button) => { button.disabled = true; }); status.textContent = "Saving the preview checkpoint…";
    try {
      await api(`/projects/${state.selected.project_id}/exports/${revisionId}/preview-review`, { method: "POST", body: JSON.stringify({ decision, surface: surface.value, tool_version: version.value.trim(), artifact_sha256: epubArtifact.sha256, notes: notes.value.trim() || null }) });
      status.textContent = "Preview result recorded in the durable replay.";
      await Promise.all([loadEvents(), loadExecution(), loadArtifacts()]);
    } catch (error) { status.textContent = `Could not save preview result: ${error.message}`; actions.querySelectorAll("button").forEach((button) => { button.disabled = false; }); }
  };
  form.addEventListener("submit", (event) => { event.preventDefault(); submit("verified"); }); issues.addEventListener("click", () => submit("issues_found"));
  actions.append(verified, issues); form.append(previewField("Preview surface", surface), previewField("Tool/version used", version), previewField("Notes", notes), actions, status);
  return form;
}
function appendPreviewCheckpoint(box, epubArtifact, revisionId) {
  if (!epubArtifact || !revisionId || !state.selected) return;
  const checkpoint = kindlePreviewCheckpoint([epubArtifact], state.events);
  const panel = document.createElement("section"); panel.className = "preview-review";
  const heading = document.createElement("h4"); heading.textContent = "Kindle preview checkpoint";
  const explanation = document.createElement("p"); explanation.className = "muted"; explanation.textContent = "Open the generated EPUB in Kindle Previewer or KDP Online Previewer, then record what you saw against this exact file. This is owner evidence, not Amazon acceptance.";
  const hash = document.createElement("code"); hash.className = "preview-review-hash"; hash.textContent = `EPUB SHA-256 ${epubArtifact.sha256}`;
  panel.append(heading, explanation, hash);
  if (checkpoint.review) {
    const previous = document.createElement("p"); previous.className = `preview-review-result preview-review-${checkpoint.status}`;
    const payload = checkpoint.review.payload || {};
    const surface = payload.surface === "kdp_online_previewer" ? "KDP Online Previewer" : "Kindle Previewer";
    previous.textContent = `Last result: ${payload.decision === "verified" ? "Verified" : "Issues found"} in ${surface}${checkpoint.review.timestamp ? ` · ${new Date(checkpoint.review.timestamp).toLocaleString()}` : ""}.${payload.notes ? ` ${payload.notes}` : ""}`;
    panel.append(previous);
  }
  panel.append(createPreviewReviewForm(epubArtifact, revisionId, checkpoint)); box.append(panel);
}
function renderExports(packageResult) {
  const box = $("#exports"); box.replaceChildren(); state.packageResult = packageResult;
  const artifacts = normalizedPackageArtifacts(packageResult);
  const heading = document.createElement("h4"); heading.textContent = `Export package · ${packageResult.title}`;
  const status = document.createElement("p"); status.className = "muted export-status"; status.textContent = `${packageResult.package_state} · ${artifacts.length} protected files. The same files are grouped in the Delivery package shelf above.`;
  box.append(heading, status);
  appendPreviewCheckpoint(box, artifacts.find((artifact) => artifact.filename === "book.epub"), packageResult.revision_id);
}
function renderPackageCheckpoint() {
  const packageArtifacts = state.artifacts.filter((artifact) => String(artifact.relative_path || "").startsWith("exports/"));
  if (packageArtifacts.length) {
    const revisionId = packageArtifacts.find((artifact) => artifact.filename === "book.epub" || artifactFilename(artifact) === "book.epub")?.revision_id || packageArtifacts[0].revision_id;
    renderExports({
      revision_id: revisionId,
      title: state.packageResult?.title || state.execution?.brief?.title || state.selected?.title || "Book",
      package_state: state.packageResult?.package_state || "structurally_validated",
      artifacts: packageArtifacts,
    });
  } else if (!state.packageResult?.artifacts?.length) {
    $("#exports")?.replaceChildren();
  }
}
function reviewStateLabel(state) { return ({ approved: "Approved", revision_requested: "Revision requested", pending: "Review pending" })[state] || "Review pending"; }
function appendArtifactReview(item, artifact) {
  const review = document.createElement("div"); review.className = "artifact-review";
  const heading = document.createElement("strong"); heading.textContent = `Owner review: ${reviewStateLabel(artifact.owner_review_state)}`; review.append(heading);
  if (artifact.owner_review_note) { const note = document.createElement("p"); note.className = "muted artifact-review-note"; note.textContent = artifact.owner_review_note; review.append(note); }
  if (artifact.owner_reviewed_at) { const reviewed = document.createElement("p"); reviewed.className = "muted artifact-review-date"; reviewed.textContent = `Reviewed ${new Date(artifact.owner_reviewed_at).toLocaleString()}`; review.append(reviewed); }
  const noteLabel = document.createElement("label"); noteLabel.textContent = "Note (optional)";
  const noteInput = document.createElement("textarea"); noteInput.rows = 2; noteInput.placeholder = "Add context for this decision"; noteInput.className = "artifact-review-note-input"; noteLabel.append(noteInput);
  const actions = document.createElement("div"); actions.className = "form-actions artifact-review-actions";
  const result = document.createElement("p"); result.className = "muted artifact-review-result"; result.setAttribute("aria-live", "polite"); result.setAttribute("role", "status");
  [["approve", "Approve", "primary"], ["request_revision", "Request revision", "quiet"]].forEach(([decision, label, className]) => {
    const button = document.createElement("button"); button.type = "button"; button.className = className; button.textContent = label;
    button.addEventListener("click", async () => {
      actions.querySelectorAll("button").forEach((control) => { control.disabled = true; }); result.textContent = `${label}…`;
      try {
        const response = await api(`/projects/${state.selected.project_id}/artifacts/${artifact.artifact_id}/review`, { method: "POST", body: JSON.stringify({ decision, note: noteInput.value.trim() || null, expected_owner_review_state: artifact.owner_review_state }) });
        result.textContent = response.revision_job_id
          ? "Review saved. One bounded artwork revision is queued; the original remains available for comparison."
          : decision === "request_revision"
            ? "Review saved as a record. This image has no production run to resume."
            : "Review saved. The artifact is now approved.";
        await Promise.all([loadArtifacts(), loadEvents(), loadExecution()]);
      }
      catch (error) { result.textContent = error.status === 409 ? "Review conflict: this artifact changed elsewhere. Reloading its current state…" : `Could not save review: ${error.message}`; actions.querySelectorAll("button").forEach((control) => { control.disabled = false; }); if (error.status === 409) await loadArtifacts(); }
    }); actions.append(button);
  });
  review.append(noteLabel, actions, result); item.append(review);
}
function renderArtifactGroups(box, artifacts, emptyText = "No files recorded yet.") {
  box.replaceChildren();
  box.className = artifacts.length ? "artifact-shelves" : "artifact-empty";
  if (!artifacts.length) { box.textContent = emptyText; return; }
  const groups = [
    ["manuscript", "Manuscript files", "Source formats and readable working files."],
    ["artwork", "Artwork", "Images awaiting or carrying an owner decision."],
    ["metadata", "Metadata", "Book data used to describe and validate the package."],
    ["package", "Delivery package", "Validated files derived from an accepted revision."],
  ];
  groups.forEach(([key, title, description]) => {
    const members = artifacts.filter((artifact) => groupArtifact(artifact) === key);
    if (!members.length) return;
    const shelf = document.createElement("section"); shelf.className = `artifact-shelf artifact-shelf-${key}`;
    const heading = document.createElement("div"); heading.className = "artifact-shelf-heading";
    const titleNode = document.createElement("h3"); titleNode.textContent = title;
    const copy = document.createElement("p"); copy.className = "muted"; copy.textContent = description;
    heading.append(titleNode, copy);
    const grid = document.createElement("div"); grid.className = "artifact-grid";
    members.forEach((artifact) => grid.append(createArtifactTile(artifact)));
    shelf.append(heading, grid); box.append(shelf);
  });
}
async function loadArtifacts() {
  if (!state.selected) return;
  const box = $("#artifacts"); revokeArtifactUrls();
  try {
    state.artifacts = await api(`/projects/${state.selected.project_id}/artifacts`);
    state.packageResult = state.artifacts.some((artifact) => String(artifact.relative_path || "").startsWith("exports/"))
      ? { revision_id: state.artifacts.find((artifact) => String(artifact.relative_path || "").startsWith("exports/"))?.revision_id, title: state.execution?.brief?.title || state.selected.title, package_state: "structurally_validated" }
      : null;
    renderArtifactGroups(box, state.artifacts, "No production artifacts loaded. Approve a brief to create the first package.");
    renderStageBoard(); renderBookOverview(); renderPackageCheckpoint();
  } catch (error) {
    state.artifacts = []; state.packageResult = null; box.className = "artifact-empty"; box.textContent = `Artifacts unavailable: ${error.message}`; renderStageBoard();
  }
}
async function loadReviews() { if (!state.selected) return; const reviews = await api(`/projects/${state.selected.project_id}/reviews`); state.reviews = reviews; const box = $("#reviews"); box.replaceChildren(); if (!reviews.length) { renderStageBoard(); return; } const heading = document.createElement("h4"); heading.textContent = "Review findings"; box.append(heading); reviews.forEach((finding) => { const item = document.createElement("p"); item.className = "review-finding"; item.textContent = `${finding.severity} · ${finding.criterion}: ${finding.evidence}${finding.resolution_revision_id ? " · resolved" : " · open"}`; box.append(item); }); renderStageBoard(); }
function quotaWindowLabel(snapshot, accountCount) { const seconds = Number(snapshot.window_seconds); const name = seconds === 18000 ? "5-hour window" : seconds === 604800 ? "7-day window" : "Provider window"; return accountCount > 1 ? `${name} · account ${snapshot.account_index}` : name; }
async function loadQuota() { const summary = $("#quota-summary"); summary.textContent = "Refreshing live Codex limits…"; try { const live = await api("/quota/live"); summary.replaceChildren(); if (!live.windows?.length) { summary.textContent = "Codex limits unavailable: no measurable live windows were returned."; return; } const accountCount = Math.max(...live.windows.map((window) => Number(window.account_index) || 1)); const source = document.createElement("p"); source.className = "muted"; source.textContent = `Live source: ${live.source} · fetched ${new Date(live.fetched_at).toLocaleString()}`; summary.append(source); live.windows.forEach((window) => { const item = document.createElement("article"); item.className = "usage-call"; const heading = document.createElement("strong"); heading.textContent = quotaWindowLabel(window, accountCount); const details = document.createElement("p"); details.className = "muted"; details.textContent = `${window.used}% used · ${window.remaining}% remaining · resets ${window.reset}`; item.append(heading, details); summary.append(item); }); } catch (error) { summary.textContent = "Codex live limits unavailable: " + error.message; } }
function displayModel(call) { const prefix = `${call.provider}/`; return call.model.startsWith(prefix) ? call.model.slice(prefix.length) : call.model; }
function displayPurpose(purpose) { return purpose.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function displayTokens(value) { return value == null ? "not reported" : Number(value).toLocaleString(); }
function renderUsageCalls(calls) {
  const summary = $("#usage-calls");
  summary.replaceChildren();
  if (!calls.length) { summary.textContent = "No provider calls recorded for this scope."; return; }
  calls.forEach((call) => {
    const item = document.createElement("article"); item.className = "usage-call";
    const heading = document.createElement("strong"); heading.textContent = `${displayPurpose(call.purpose)} · ${displayModel(call)}`;
    const meta = document.createElement("p"); meta.className = "muted"; meta.textContent = `${call.outcome} · ${displayTokens(call.input_tokens)} input · ${displayTokens(call.output_tokens)} output · subscription billing not reported`;
    const lineage = document.createElement("details"); const summaryLine = document.createElement("summary"); summaryLine.textContent = "Show lineage"; const id = document.createElement("code"); id.textContent = `${call.provider} · ${call.call_id}`; lineage.append(summaryLine, id);
    item.append(heading, meta, lineage); summary.append(item);
  });
}
async function loadUsage() {
  const summary = $("#usage-summary");
  try {
    const scope = state.selected ? `?project_id=${state.selected.project_id}` : "";
    const usage = await api(`/usage${scope}`);
    summary.replaceChildren();
    const calls = document.createElement("p");
    const count = document.createElement("strong"); count.textContent = usage.calls;
    calls.append(count, ` ${state.selected ? "project" : "workspace"} calls recorded`);
    const tokens = document.createElement("p"); tokens.textContent = `Input tokens: ${displayTokens(usage.input_tokens)} · Output tokens: ${displayTokens(usage.output_tokens)} · Reasoning tokens: ${displayTokens(usage.reasoning_tokens)}`;
    const note = document.createElement("p"); note.className = "muted"; note.textContent = "Subscription billing is not reported by the provider.";
    summary.append(calls, tokens, note);
    try { renderUsageCalls(await api(`/usage/calls${scope}`)); } catch { renderUsageCalls([]); }
    await loadQuota();
  } catch (error) { summary.textContent = error.message; }
}

document.querySelectorAll(".nav-button").forEach((button) => button.addEventListener("click", () => { document.querySelectorAll(".nav-button").forEach((other) => other.classList.toggle("active", other === button)); document.querySelectorAll(".view").forEach((view) => view.classList.toggle("active", view.id === `${button.dataset.view}-view`)); if (button.dataset.view === "usage") loadUsage().catch((error) => { $("#usage-summary").textContent = error.message; }); }));
$("#new-project-button").addEventListener("click", () => $("#project-form").classList.toggle("hidden"));
document.querySelectorAll("[data-cancel]").forEach((button) => button.addEventListener("click", () => $(`#${button.dataset.cancel}`).classList.add("hidden")));
$("#project-form").addEventListener("submit", async (event) => { event.preventDefault(); try { const form = new FormData(event.target); const project = await api("/projects", { method: "POST", body: JSON.stringify(Object.fromEntries(form)) }); event.target.reset(); event.target.classList.add("hidden"); await loadProjects(); await selectProject(project); } catch (error) { showError("#project-form-error", error); } });
$("#message-form").addEventListener("submit", async (event) => { event.preventDefault(); if (!state.selected) return; const input = $("#message-input"); const content = input.value.trim(); if (!content) return; const external_dedupe_id = crypto.randomUUID(); try { await api(`/projects/${state.selected.project_id}/messages`, { method: "POST", body: JSON.stringify({ conversation_id: state.selected.conversation_id, channel: "dashboard", external_dedupe_id, content }) }); input.value = ""; await loadMessages(); await loadEvents(); } catch (error) { window.alert(error.message); } });
$("#brief-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.selected) return;
  const form = new FormData(event.target);
  const pages = form.get("length_mode") === "pages";
  const minimum = Number(form.get(pages ? "minimum_pages" : "minimum_words"));
  const maximum = Number(form.get(pages ? "maximum_pages" : "maximum_words"));
  const formats = form.getAll("output_formats").map(String);
  const result = $("#brief-result");
  if (!Number.isInteger(minimum) || !Number.isInteger(maximum) || minimum < 1 || minimum > maximum) { result.textContent = "Enter a positive range where the minimum does not exceed the maximum."; return; }
  if (!formats.length) { result.textContent = "Choose at least one output format."; return; }
  const target = pages ? { target_pages: { minimum, maximum } } : { target_length: { minimum_words: minimum, maximum_words: maximum } };
  const structured_brief = {
    profile: state.selected.profile,
    title: String(form.get("title") || state.selected.title).trim(),
    genre: String(form.get("genre") || state.selected.profile).trim(),
    author: String(form.get("author") || "").trim(),
    language: String(form.get("language") || state.selected.language || "en").trim(),
    audience: String(form.get("audience") || "General readers").trim(),
    promise_or_premise: String(form.get("promise") || "").trim(),
    description: String(form.get("description") || "").trim(),
    keywords: String(form.get("keywords") || "").split(",").map((keyword) => keyword.trim()).filter(Boolean).slice(0, 24),
    art_direction: String(form.get("art_direction") || "").trim(),
    output_formats: formats,
    ...target,
  };
  try {
    const brief = await api(`/projects/${state.selected.project_id}/briefs`, { method: "POST", body: JSON.stringify({ structured_brief }) });
    event.target.dataset.dirty = "false";
    result.replaceChildren();
    const saved = document.createElement("p"); saved.textContent = "Brief revision saved. Review the exact hash before it becomes a production run.";
    const hash = document.createElement("code"); hash.textContent = brief.content_hash; saved.append(" ", hash);
    const approve = document.createElement("button"); approve.type = "button"; approve.className = "primary"; approve.textContent = "Approve exact revision";
    const status = document.createElement("p"); status.className = "muted"; status.setAttribute("role", "status");
    result.append(saved, approve, status);
    await loadExecution();
    approve.addEventListener("click", async () => {
      approve.disabled = true; status.textContent = "Approving the exact saved revision and creating the durable task plan…";
      try {
        const maxTurns = pages ? 24 : 8;
        const approved = await api(`/projects/${state.selected.project_id}/briefs/${brief.brief_id}/approve`, { method: "POST", body: JSON.stringify({ expected_content_hash: brief.content_hash, budget: { max_turns: maxTurns } }) });
        status.textContent = `Run ${approved.run_id} is queued. Its task plan will appear in the control room.`;
        await loadProjects();
        state.selected = state.projects.find((candidate) => candidate.project_id === state.selected.project_id) || state.selected;
        await Promise.all([loadEvents(), loadExecution(), loadSections(), loadArtifacts()]);
      } catch (error) { status.textContent = `Approval failed: ${error.message}`; approve.disabled = false; }
    });
  } catch (error) { result.textContent = error.message; }
});
$("#refresh-catalog").addEventListener("click", () => loadCatalog().then(() => loadProviders()).catch((error) => { $("#catalog-status").textContent = error.message; }));
$("#refresh-events").addEventListener("click", () => loadEvents().catch((error) => window.alert(error.message)));
$("#export-current").addEventListener("click", () => buildCurrentPackage());
$("#refresh-usage").addEventListener("click", () => loadUsage().catch((error) => window.alert(error.message)));
$("#provider-form").addEventListener("submit", async (event) => { event.preventDefault(); const form = new FormData(event.target); const values = Object.fromEntries(form); const mismatched = [values.orchestration_model, values.drafting_model, values.review_model].some((model) => model && state.catalog?.models.some((entry) => entry.qualified_model === model && entry.provider !== values.provider)); if (mismatched) { $("#provider-result").textContent = "Choose models belonging to the selected provider."; return; } try { await api(`/providers/${encodeURIComponent(values.provider)}`, { method: "PUT", body: JSON.stringify(values) }); $("#provider-result").textContent = "Metadata saved; credential bytes remain outside PostgreSQL."; await loadProviders(); } catch (error) { $("#provider-result").textContent = error.message; } });
async function loadProviders() { const providers = await api("/providers"); const list = $("#provider-list"); list.replaceChildren(); if (!providers.length) { const empty = document.createElement("p"); empty.className = "muted"; empty.textContent = "No provider metadata saved."; list.append(empty); return; } providers.forEach((provider) => { const item = document.createElement("div"); const line = document.createElement("p"); const name = document.createElement("strong"); name.textContent = provider.provider; line.append(name, ` · ${provider.protocol || "protocol not set"} · ${provider.credential_configured ? "credential reference set" : "credential not configured"}`); const button = document.createElement("button"); button.className = "quiet"; button.type = "button"; button.textContent = "Test connection"; button.addEventListener("click", () => testProviderConnection(provider.provider, button)); item.append(line, button); list.append(item); }); }
async function testProviderConnection(provider, button) { const status = $("#provider-result"); button.disabled = true; status.textContent = `Testing ${provider}…`; try { const result = await api(`/providers/${encodeURIComponent(provider)}/connection-test`, { method: "POST", body: "{}" }); const details = result.http_status ? ` · HTTP ${result.http_status}` : ""; status.textContent = `${provider}: ${result.outcome}${details}${result.response_id ? ` · response ${result.response_id}` : ""}`; } catch (error) { status.textContent = `${provider}: ${error.message}`; } finally { button.disabled = false; } }
async function loadTelegramStatus() { const status = $("#telegram-status"); try { const telegram = await api("/telegram/status"); status.textContent = telegram.configured ? `Configured · ${telegram.linked_chat_count} owner chat(s) · ${telegram.linked_project_count} project link(s) · next update ${telegram.next_update_id}` : "Not configured. Set the local bot token and allowlisted chat/sender IDs; no credentials are shown here."; } catch (error) { status.textContent = error.message; } }
$("#refresh-telegram").addEventListener("click", () => loadTelegramStatus());
$("#telegram-link-form").addEventListener("submit", async (event) => { event.preventDefault(); const result = $("#telegram-link-result"); const button = $("#telegram-link-button"); const input = $("#telegram-chat-id"); result.textContent = ""; input.setAttribute("aria-invalid", "false"); if (!state.selected) { result.textContent = "Select a project in Studio first, then try linking again."; return; } const project = state.selected; const chatId = Number(new FormData(event.target).get("chat_id")); if (!Number.isSafeInteger(chatId)) { input.setAttribute("aria-invalid", "true"); result.textContent = "Enter a valid numeric Telegram chat ID."; return; } button.disabled = true; result.textContent = `Setting ${project.title} active for chat ${chatId}…`; try { const telegram = await api(`/projects/${project.project_id}/telegram/link`, { method: "POST", body: JSON.stringify({ chat_id: chatId }) }); result.textContent = `Chat ${chatId} now uses ${project.title}; all projects remain linked. ${telegram.linked_project_count} project link(s) active.`; await loadTelegramStatus(); } catch (error) { let detail = error.message || "request failed"; try { const parsed = JSON.parse(detail); detail = parsed.detail || detail; } catch { /* API may return plain text */ } result.textContent = `Could not set chat ${chatId}: ${detail}`; } finally { button.disabled = false; } });
document.querySelectorAll("#brief-form [name=length_mode]").forEach((radio) => radio.addEventListener("change", (event) => { $("#page-target-fields").classList.toggle("hidden", event.target.value !== "pages"); $("#word-target-fields").classList.toggle("hidden", event.target.value !== "words"); }));
document.querySelectorAll("#brief-form input, #brief-form textarea, #brief-form select").forEach((control) => control.addEventListener("input", () => { $("#brief-form").dataset.dirty = "true"; }));
async function boot() { $("#auth-view").classList.add("hidden"); $("#app-shell").classList.remove("hidden"); bindCatalogCoherence(); await loadProjects(); await loadCatalog(); await loadProviders(); const savedProviders = await api("/providers"); const saved = savedProviders.find((provider) => provider.provider === $("#provider-select").value) || savedProviders[0] || {}; populateCatalogSelects(saved); savedProviders.slice(1).forEach((provider) => addSavedOption($("#provider-select"), provider.provider, "Provider")); if (saved.provider) filterCatalogModels(saved.provider); await loadTelegramStatus(); }
$("#auth-form").addEventListener("submit", async (event) => { event.preventDefault(); const error = $("#auth-error"); error.textContent = ""; const token = $("#owner-token").value; try { await fetch("/auth/login", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ token }) }).then(async (response) => { if (!response.ok) throw new Error((await response.text()).slice(0, 240)); }); sessionStorage.setItem("ebook-factory-owner-token", token); $("#owner-token").value = ""; await boot(); } catch (reason) { error.textContent = reason.message || "Sign in failed"; } });
if (ownerToken()) { api("/auth/verify").then(boot).catch(() => sessionStorage.removeItem("ebook-factory-owner-token")); }
