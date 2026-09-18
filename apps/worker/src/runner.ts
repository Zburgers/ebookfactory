import { runPiProduction } from "./production.ts";

const MAX_RESPONSE_BYTES = 64 * 1024;
const DEFAULT_PROVIDER = "openai-codex";
const DEFAULT_REQUEST_TIMEOUT_MS = 10_000;

/** Build the trusted executor that turns one leased job into a fenced production result. */
export function createProductionExecutor({
  baseUrl,
  token,
  workerId,
  provider = DEFAULT_PROVIDER,
  runProduction = runPiProduction,
  requestTimeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
}) {
  if (!baseUrl || !token || !workerId) throw new Error("baseUrl, token, and workerId are required");
  if (!provider || typeof provider !== "string") throw new Error("provider is required");
  return async (lease, { signal } = {}) => {
    const context = await requestJson(baseUrl, token, `/private/worker/jobs/${encodeURIComponent(lease.job_id)}/context`, {
      method: "GET",
      headers: {
        "x-ebook-worker-token": token,
        "x-worker-id": workerId,
        "x-generation": String(lease.generation),
      },
      signal,
      requestTimeoutMs,
    });
    const providers = await requestJson(baseUrl, token, "/private/worker/providers", { method: "GET", signal, requestTimeoutMs });
    const configured = providers?.find((entry) => entry?.provider === provider && entry?.scope === "app");
    if (configured?.protocol !== "pi-native") throw new Error(`provider ${provider} does not support pi-native execution`);
    const model = configured?.orchestration_model || configured?.drafting_model || configured?.review_model;
    if (!configured || !model) throw new Error(`configured provider ${provider} has no usable model`);
    const result = await runProduction({ context, model, signal });
    if (!result?.text || !result.callId) {
      throw new Error("Pi production returned an incomplete result");
    }
    const configuredModelSuffix = model.includes("/") ? model.slice(model.lastIndexOf("/") + 1) : model;
    const modelMatches = !result.model || result.model === model || result.model === configuredModelSuffix;
    if ((result.provider && result.provider !== provider) || !modelMatches) {
      throw new Error("Pi production provider or model conflicted with saved configuration");
    }
    await requestJson(baseUrl, token, "/private/worker/production-result", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        job_id: lease.job_id,
        worker_id: workerId,
        generation: lease.generation,
        content: result.text,
        provider,
        model,
        call_id: result.callId,
        usage: result.usage ?? null,
      }),
      signal,
      requestTimeoutMs,
    });
    return { terminal: true };
  };
}

async function requestJson(baseUrl, token, path, options) {
  const { requestTimeoutMs = DEFAULT_REQUEST_TIMEOUT_MS, signal, ...fetchOptions } = options;
  const requestController = new AbortController();
  const abortRequest = () => requestController.abort();
  const timeout = setTimeout(() => requestController.abort(), requestTimeoutMs);
  signal?.addEventListener("abort", abortRequest, { once: true });
  if (signal?.aborted) abortRequest();
  try {
    const response = await fetch(`${baseUrl}${path}`, {
    ...fetchOptions,
    headers: { "x-ebook-worker-token": token, ...(options.headers || {}) },
      signal: requestController.signal,
    });
    const bytes = await readBounded(response);
    if (!response.ok) throw new Error(`worker API ${response.status}: ${bytes.slice(0, 240)}`);
    if (!bytes) return null;
    try {
      return JSON.parse(bytes);
    } catch {
      throw new Error("worker API returned malformed JSON");
    }
  } catch (error) {
    if (requestController.signal.aborted && !signal?.aborted) throw new Error("worker API request timed out");
    throw error;
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", abortRequest);
  }
}

async function readBounded(response) {
  const reader = response.body?.getReader();
  if (!reader) return "";
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_RESPONSE_BYTES) {
        await reader.cancel();
        throw new Error("worker API response exceeded limit");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  return new TextDecoder().decode(Buffer.concat(chunks.map((chunk) => Buffer.from(chunk))));
}
