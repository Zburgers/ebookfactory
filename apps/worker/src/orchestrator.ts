import { runPiProduction } from "./production.ts";
import { requestJson } from "./runner.ts";

const DEFAULT_POLL_MS = 1000;
const DEFAULT_PROVIDER = "openai-codex";

export function createOrchestratorExecutor({ baseUrl, token, workerId, provider = DEFAULT_PROVIDER, runProduction = runPiProduction }) {
  if (!baseUrl || !token || !workerId) throw new Error("baseUrl, token, and workerId are required");
  return async (lease, { signal } = {}) => {
    const headers = { "x-worker-id": workerId, "x-generation": String(lease.generation) };
    const context = await requestJson(baseUrl, token, `/private/orchestrator/${encodeURIComponent(lease.turn_id)}/context`, { method: "GET", headers, signal });
    const providers = await requestJson(baseUrl, token, "/private/worker/providers", { method: "GET", signal });
    const configured = providers?.find((entry) => entry?.provider === provider && entry?.scope === "app");
    if (!configured || configured.protocol !== "pi-native") throw new Error(`provider ${provider} is not a supported pi-native app provider`);
    const model = configured.orchestration_model;
    if (!model) throw new Error(`configured provider ${provider} has no orchestration model`);
    const result = await runProduction({ context, model, signal });
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

export async function runOrchestratorWorker({ baseUrl, token, workerId, provider, runProduction, pollMs = DEFAULT_POLL_MS, signal }) {
  const execute = createOrchestratorExecutor({ baseUrl, token, workerId, provider, runProduction });
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
    try { await execute(lease, { signal: executionController.signal }); } catch { /* the lease becomes retryable after expiry */ }
    finally { clearInterval(heartbeatTimer); signal?.removeEventListener("abort", abortFromParent); }
  }
}
