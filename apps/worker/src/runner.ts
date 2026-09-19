import { runPiProduction } from "./production.ts";
import { runCodexArt } from "./codex-art.ts";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";

const MAX_RESPONSE_BYTES = 64 * 1024;
const DEFAULT_PROVIDER = "openai-codex";
const DEFAULT_REQUEST_TIMEOUT_MS = 10_000;
const MAX_ART_BYTES = 10 * 1024 * 1024;
const ART_MIME_BY_EXTENSION = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp" };

function normalizeUsage(usage) {
  if (!usage) return null;
  return {
    input_tokens: usage.input_tokens ?? usage.inputTokens ?? usage.input ?? null,
    output_tokens: usage.output_tokens ?? usage.outputTokens ?? usage.output ?? null,
    cache_read_tokens: usage.cache_read_tokens ?? usage.cacheReadTokens ?? usage.cacheRead ?? null,
    cache_write_tokens: usage.cache_write_tokens ?? usage.cacheWriteTokens ?? usage.cacheWrite ?? null,
    reasoning_tokens: usage.reasoning_tokens ?? usage.reasoningTokens ?? usage.reasoning ?? null,
  };
}

/** Build the trusted executor that turns one leased job into a fenced production result. */
export function createProductionExecutor({
  baseUrl,
  token,
  workerId,
  provider = DEFAULT_PROVIDER,
  runProduction = runPiProduction,
  runArt = runCodexArt,
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
    const model = context.task_type === "review"
      ? (configured?.review_model || configured?.drafting_model || configured?.orchestration_model)
      : context.task_type === "outline"
        ? (configured?.orchestration_model || configured?.drafting_model || configured?.review_model)
        : (configured?.drafting_model || configured?.orchestration_model || configured?.review_model);
    if (!configured || !model) throw new Error(`configured provider ${provider} has no usable model`);
    const result = await runProduction({ context, model, thinking: "low", taskType: context.task_type, signal });
    if (!result?.text || !result.callId) {
      throw new Error("Pi production returned an incomplete result");
    }
    const configuredModelSuffix = model.includes("/") ? model.slice(model.lastIndexOf("/") + 1) : model;
    const modelMatches = !result.model || result.model === model || result.model === configuredModelSuffix;
    if ((result.provider && result.provider !== provider) || !modelMatches) {
      throw new Error("Pi production provider or model conflicted with saved configuration");
    }
    if (context.task_type === "outline" || context.task_type === "review") {
      await requestJson(baseUrl, token, "/private/worker/task-result", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          job_id: lease.job_id, worker_id: workerId, generation: lease.generation,
          result: result.text, provider, model, call_id: result.callId, usage: result.usage ?? null,
        }),
        signal, requestTimeoutMs,
      });
      return { terminal: true };
    }
    const art = context.brief?.art_direction
      ? await readGeneratedArt(await runArt({ prompt: context.brief.art_direction, model, signal }), signal)
      : null;
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
        ...(art ? { art } : {}),
      }),
      signal,
      requestTimeoutMs,
    });
    return { terminal: true };
  };
}

async function readGeneratedArt(result, signal) {
  if (!result?.savedPath || path.isAbsolute(result.savedPath) === false) throw new Error("Codex art adapter returned an invalid savedPath");
  const extension = path.extname(result.savedPath).toLowerCase();
  const mimeType = ART_MIME_BY_EXTENSION[extension];
  if (!mimeType) throw new Error("Codex art adapter returned an unsupported image type");
  const info = await stat(result.savedPath);
  if (!info.isFile() || info.size > MAX_ART_BYTES) throw new Error("Codex art output exceeded the bounded file limit");
  if (signal?.aborted) throw new Error("Codex art aborted");
  const bytes = await readFile(result.savedPath);
  if (bytes.length > MAX_ART_BYTES) throw new Error("Codex art output exceeded the bounded file limit");
  return {
    filename: path.basename(result.savedPath),
    mime_type: mimeType,
    byte_count: bytes.length,
    content_base64: bytes.toString("base64"),
    ...(result.callId ? { call_id: result.callId } : {}),
    ...(result.providerRequestId ? { provider_request_id: result.providerRequestId } : {}),
    ...(result.usage ? { usage: normalizeUsage(result.usage) } : {}),
  };
}

export async function requestJson(baseUrl, token, path, options) {
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
