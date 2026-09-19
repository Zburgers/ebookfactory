/** Trusted host adapter for the installed Codex app-server image-generation route. */

import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";

const CLIENT_INFO = { name: "ebook-factory-art", title: "Ebook Factory", version: "0.1.0" };

export function buildCodexInitialize() {
  return {
    method: "initialize",
    id: 0,
    params: { clientInfo: CLIENT_INFO, capabilities: { experimentalApi: true } },
  };
}

export function buildCodexThreadStart(model) {
  const modelId = model.includes("/") ? model.slice(model.lastIndexOf("/") + 1) : model;
  return { method: "thread/start", id: 1, params: { model: modelId } };
}

export function buildCodexArtTurn(threadId, prompt) {
  if (!threadId || !prompt) throw new Error("Codex art thread and prompt are required");
  return {
    method: "turn/start",
    id: 2,
    params: { threadId, input: [{ type: "text", text: prompt }] },
  };
}

export function parseCodexArtEvent(line) {
  try {
    const event = JSON.parse(line);
    const item = event.params?.item;
    if (item?.type !== "imageGeneration") return null;
    return {
      status: item.status,
      savedPath: item.saved_path || item.savedPath || null,
      result: item.result || null,
      failure: item.failure || null,
    };
  } catch {
    return null;
  }
}

const DEFAULT_TIMEOUT_MS = 120_000;
const MAX_ERROR_LENGTH = 500;

function boundedError(message) {
  return String(message)
    .replace(/(Bearer\s+)[^\s]+/gi, "$1[redacted]")
    .replace(/(api[_-]?key|access[_-]?token|client[_-]?secret|password|secret)\s*[=:]\s*[^\s,;]+/gi, "$1=[redacted]")
    .slice(0, MAX_ERROR_LENGTH);
}

export function runCodexArt({ prompt, model = "gpt-5.6-luna", command = "codex", commandArgs = ["app-server"], cwd, signal, timeoutMs = DEFAULT_TIMEOUT_MS, spawnProcess = spawn }) {
  const boundedTimeout = Number.isFinite(timeoutMs) && timeoutMs > 0 ? Math.min(timeoutMs, DEFAULT_TIMEOUT_MS) : DEFAULT_TIMEOUT_MS;
  const callId = randomUUID();
  const child = spawnProcess(command, commandArgs, { cwd, shell: false, stdio: ["pipe", "pipe", "pipe"] });
  return new Promise((resolve, reject) => {
    let stderr = "";
    let buffer = "";
    let threadId = null;
    let usage = null;
    let providerRequestId = null;
    let settled = false;
    let timer;
    const terminate = () => { if (!child.killed) child.kill("SIGTERM"); };
    const finish = (error, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
      terminate();
      error ? reject(error) : resolve(value);
    };
    const onAbort = () => finish(new Error("Codex art request aborted"));
    timer = setTimeout(() => finish(new Error(`Codex art request timed out after ${boundedTimeout}ms`)), boundedTimeout);
    if (signal?.aborted) return onAbort();
    signal?.addEventListener("abort", onAbort, { once: true });
    const send = (message) => child.stdin.write(`${JSON.stringify(message)}\n`);
    child.on("error", (error) => finish(new Error(boundedError(error.message))));
    child.stderr.on("data", (chunk) => { stderr = `${stderr}${chunk}`.slice(-2000); });
    child.stdout.on("data", (chunk) => {
      buffer += chunk.toString();
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        let event;
        try { event = JSON.parse(line); } catch { continue; }
        if (event.id === 0 && event.result) { send({ method: "initialized", params: {} }); send(buildCodexThreadStart(model)); }
        else if (event.id === 1 && event.result?.thread?.id) { threadId = event.result.thread.id; send(buildCodexArtTurn(threadId, prompt)); }
        else if (event.error) finish(new Error(boundedError(`Codex app-server error: ${event.error.message || "unknown"}`)));
        if (event.method === "rawResponse/completed") {
          providerRequestId = event.params?.responseId || providerRequestId;
          usage = event.params?.usage || usage;
        }
        const art = parseCodexArtEvent(line);
        if (art?.status === "completed" && art.savedPath) finish(null, { ...art, callId, providerRequestId, usage });
        if (art?.status === "failed" || art?.failure) finish(new Error(boundedError(`Codex image generation failed: ${JSON.stringify(art.failure || art.result)}`)));
      }
    });
    child.on("close", (code) => { if (!settled) finish(new Error(boundedError(`Codex app-server exited with code ${code}: ${stderr.trim()}`))); });
    send(buildCodexInitialize());
  });
}
