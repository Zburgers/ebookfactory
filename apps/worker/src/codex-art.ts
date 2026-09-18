/** Trusted host adapter for the installed Codex app-server image-generation route. */

import { spawn } from "node:child_process";

const CLIENT_INFO = { name: "ebook-factory-art", title: "Ebook Factory", version: "0.1.0" };

export function buildCodexInitialize() {
  return {
    method: "initialize",
    id: 0,
    params: { clientInfo: CLIENT_INFO, capabilities: { experimentalApi: true } },
  };
}

export function buildCodexThreadStart(model) {
  return { method: "thread/start", id: 1, params: { model } };
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

export function runCodexArt({ prompt, model = "gpt-5.6-luna", command = "codex", commandArgs = ["app-server"], cwd }) {
  const child = spawn(command, commandArgs, { cwd, shell: false, stdio: ["pipe", "pipe", "pipe"] });
  return new Promise((resolve, reject) => {
    let stderr = "";
    let buffer = "";
    let threadId = null;
    let settled = false;
    const finish = (error, value) => {
      if (settled) return;
      settled = true;
      child.kill("SIGTERM");
      error ? reject(error) : resolve(value);
    };
    const send = (message) => child.stdin.write(`${JSON.stringify(message)}\n`);
    child.on("error", (error) => finish(error));
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
        else if (event.error) finish(new Error(`Codex app-server error: ${event.error.message || "unknown"}`));
        const art = parseCodexArtEvent(line);
        if (art?.status === "completed" && art.savedPath) finish(null, art);
        if (art?.status === "failed" || art?.failure) finish(new Error(`Codex image generation failed: ${JSON.stringify(art.failure || art.result)}`));
      }
    });
    child.on("close", (code) => { if (!settled) finish(new Error(`Codex app-server exited with code ${code}: ${stderr.trim()}`)); });
    send(buildCodexInitialize());
  });
}
