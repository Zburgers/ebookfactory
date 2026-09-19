import { ORCHESTRATOR_SYSTEM_PROMPT, runPiProduction } from "./production.ts";
import { requestJson } from "./runner.ts";
import { fileURLToPath } from "node:url";

const DEFAULT_POLL_MS = 1000;
const DEFAULT_PROVIDER = "openai-codex";
const ORCHESTRATOR_EXTENSION_PATH = fileURLToPath(new URL("./orchestrator-tools.mjs", import.meta.url));
const ORCHESTRATOR_TOOL_ALLOWLIST = ["factory_read_state", "factory_mark_gate", "factory_spawn_agent"];

function activityFromPiEvent(event) {
  if (!event?.type) return null;
  if (event.type === "tool_execution_start") return {
    activity_type: "tool.started",
    payload: { tool_call_id: event.toolCallId, tool_name: event.toolName, arguments: event.args },
  };
  if (event.type === "tool_execution_update") return {
    activity_type: "tool.updated",
    payload: { tool_call_id: event.toolCallId, tool_name: event.toolName, result: event.result },
  };
  if (event.type === "tool_execution_end") return {
    activity_type: event.isError ? "tool.failed" : "tool.completed",
    payload: { tool_call_id: event.toolCallId, tool_name: event.toolName, result: event.result, error: event.isError || undefined },
  };
  if (event.type === "message_update" && event.delta) return {
    activity_type: "message.delta",
    payload: { delta: event.delta },
  };
  if (event.type === "message_start") return { activity_type: "message.started", payload: {} };
  if (event.type === "message_end") return {
    activity_type: "message.completed",
    payload: { text: event.text },
  };
  return null;
}

export function createOrchestratorExecutor({ baseUrl, token, workerId, provider = DEFAULT_PROVIDER, runProduction = runPiProduction, skillPaths = [] }) {
  if (!baseUrl || !token || !workerId) throw new Error("baseUrl, token, and workerId are required");
  return async (lease, { signal } = {}) => {
    const headers = { "x-worker-id": workerId, "x-generation": String(lease.generation) };
    const context = await requestJson(baseUrl, token, `/private/orchestrator/${encodeURIComponent(lease.turn_id)}/context`, { method: "GET", headers, signal });
    const providers = await requestJson(baseUrl, token, "/private/worker/providers", { method: "GET", signal });
    const configured = providers?.find((entry) => entry?.provider === provider && entry?.scope === "app");
    if (!configured || configured.protocol !== "pi-native") throw new Error(`provider ${provider} is not a supported pi-native app provider`);
    const model = configured.orchestration_model;
    if (!model) throw new Error(`configured provider ${provider} has no orchestration model`);
    const result = await runProduction({
      context,
      model,
      skillPaths,
      extensionPaths: [ORCHESTRATOR_EXTENSION_PATH],
      toolAllowlist: ORCHESTRATOR_TOOL_ALLOWLIST,
      noBuiltinTools: true,
      env: {
        EBOOK_FACTORY_API_URL: baseUrl,
        EBOOK_FACTORY_WORKER_TOKEN: token,
        EBOOK_FACTORY_WORKER_ID: workerId,
        EBOOK_FACTORY_TURN_ID: lease.turn_id,
        EBOOK_FACTORY_GENERATION: String(lease.generation),
      },
      systemPrompt: ORCHESTRATOR_SYSTEM_PROMPT,
      signal,
      onTextDelta: (delta) => requestJson(baseUrl, token, "/private/orchestrator/delta", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ turn_id: lease.turn_id, worker_id: workerId, generation: lease.generation, delta }),
        signal,
      }),
      onEvent: async (event) => {
        const activity = activityFromPiEvent(event);
        if (!activity) return;
        await requestJson(baseUrl, token, "/private/orchestrator/activity", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            turn_id: lease.turn_id,
            worker_id: workerId,
            generation: lease.generation,
            ...activity,
          }),
          signal,
        });
      },
    });
    const suffix = model.includes("/") ? model.slice(model.lastIndexOf("/") + 1) : model;
    if ((result.provider && result.provider !== provider) || (result.model && result.model !== model && result.model !== suffix)) {
      throw new Error("Pi production provider or model conflicted with saved configuration");
    }
    await requestJson(baseUrl, token, "/private/orchestrator/result", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ turn_id: lease.turn_id, worker_id: workerId, generation: lease.generation, content: result.text, provider, model, call_id: result.callId, usage: result.usage ?? null }),
      signal,
    });
    return { terminal: true };
  };
}

export async function runOrchestratorWorker({ baseUrl, token, workerId, provider, runProduction, skillPaths = [], pollMs = DEFAULT_POLL_MS, signal }) {
  const execute = createOrchestratorExecutor({ baseUrl, token, workerId, provider, runProduction, skillPaths });
  while (!signal?.aborted) {
    const lease = await requestJson(baseUrl, token, "/private/orchestrator/claim", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ worker_id: workerId }) });
    if (!lease) { await new Promise((resolve) => setTimeout(resolve, pollMs)); continue; }
    const executionController = new AbortController();
    const abortFromParent = () => executionController.abort();
    signal?.addEventListener("abort", abortFromParent, { once: true });
    if (signal?.aborted) executionController.abort();
    let heartbeatFailures = 0;
    const heartbeatTick = async () => {
      if (executionController.signal.aborted) return;
      try {
        await requestJson(baseUrl, token, "/private/orchestrator/heartbeat", { method: "POST", body: JSON.stringify({ turn_id: lease.turn_id, worker_id: workerId, generation: lease.generation, lease_seconds: 60 }), signal: executionController.signal });
        heartbeatFailures = 0;
      } catch {
        if (!executionController.signal.aborted && ++heartbeatFailures >= 3) executionController.abort();
      }
    };
    const heartbeatTimer = setInterval(heartbeatTick, 20_000);
    try {
      await execute(lease, { signal: executionController.signal });
    } catch (error) {
      if (!executionController.signal.aborted && !signal?.aborted) {
        try {
          await requestJson(baseUrl, token, "/private/orchestrator/failure", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              turn_id: lease.turn_id,
              worker_id: workerId,
              generation: lease.generation,
              error: error instanceof Error ? error.message : String(error),
            }),
            signal,
          });
        } catch {
          // A lost lease or unavailable API cannot safely be retried by this attempt.
        }
      }
    }
    finally { clearInterval(heartbeatTimer); signal?.removeEventListener("abort", abortFromParent); }
  }
}
