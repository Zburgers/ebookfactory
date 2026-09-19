const API_URL = process.env.EBOOK_FACTORY_API_URL || "http://127.0.0.1:6969";
const WORKER_TOKEN = process.env.EBOOK_FACTORY_WORKER_TOKEN;
const WORKER_ID = process.env.EBOOK_FACTORY_WORKER_ID;
const TURN_ID = process.env.EBOOK_FACTORY_TURN_ID;
const GENERATION = process.env.EBOOK_FACTORY_GENERATION;
const MAX_RESPONSE_BYTES = 64 * 1024;

function requireContext() {
  if (!WORKER_TOKEN || !WORKER_ID || !TURN_ID || !GENERATION) throw new Error("orchestrator tool context is unavailable");
}

async function requestJson(path, options = {}) {
  requireContext();
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "x-ebook-worker-token": WORKER_TOKEN,
      "x-worker-id": WORKER_ID,
      "x-generation": GENERATION,
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  if (text.length > MAX_RESPONSE_BYTES) throw new Error("orchestrator tool response exceeded limit");
  if (!response.ok) throw new Error(`orchestrator tool request failed (${response.status})`);
  if (!text) return null;
  return JSON.parse(text);
}

function result(value) {
  const text = JSON.stringify(value, null, 2);
  return { content: [{ type: "text", text: text.length > MAX_RESPONSE_BYTES ? `${text.slice(0, MAX_RESPONSE_BYTES)}\n[truncated]` : text }], details: {} };
}

const stringSchema = (description) => ({ type: "string", description });

export default function registerOrchestratorTools(pi) {
  pi.registerTool({
    name: "factory_read_state",
    label: "Read project state",
    description: "Read the current durable state, events, gates, agents, and artifacts for this project.",
    parameters: { type: "object", properties: { focus: stringSchema("Optional focus such as gates, agents, artifacts, or conversation") }, additionalProperties: false },
    async execute(_toolCallId, params) {
      const focus = typeof params?.focus === "string" ? `?focus=${encodeURIComponent(params.focus.slice(0, 80))}` : "";
      return result(await requestJson(`/private/orchestrator/${encodeURIComponent(TURN_ID)}/state${focus}`));
    },
  });

  pi.registerTool({
    name: "factory_mark_gate",
    label: "Mark workflow gate",
    description: "Record a durable workflow gate status for the current project. This does not approve owner-only gates.",
    parameters: {
      type: "object",
      properties: {
        gate: { type: "string", enum: ["brief", "outline", "draft", "review", "art", "export", "kindle_preview", "owner"] },
        status: { type: "string", enum: ["pending", "in_progress", "complete", "blocked", "needs_review"] },
        note: stringSchema("Short explanation of the gate status"),
        evidence: stringSchema("Short evidence reference, such as an artifact or event"),
      },
      required: ["gate", "status"],
      additionalProperties: false,
    },
    async execute(_toolCallId, params) {
      return result(await requestJson("/private/orchestrator/gate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ turn_id: TURN_ID, worker_id: WORKER_ID, generation: Number(GENERATION), ...params }),
      }));
    },
  });

  pi.registerTool({
    name: "factory_spawn_agent",
    label: "Queue project agent",
    description: "Queue one bounded project-scoped research, review, or section-draft agent. The agent returns a durable result to the project.",
    parameters: {
      type: "object",
      properties: {
        role: { type: "string", enum: ["research", "review", "section-draft"] },
        instruction: { type: "string", minLength: 1, maxLength: 8000 },
        context: { type: "object", additionalProperties: true },
      },
      required: ["role", "instruction"],
      additionalProperties: false,
    },
    async execute(_toolCallId, params) {
      return result(await requestJson("/private/orchestrator/spawn", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ turn_id: TURN_ID, worker_id: WORKER_ID, generation: Number(GENERATION), ...params }),
      }));
    },
  });
}
