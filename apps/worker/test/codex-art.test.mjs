import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { buildCodexArtTurn, buildCodexInitialize, buildCodexThreadStart, parseCodexArtEvent, runCodexArt } from "../src/codex-art.ts";

test("builds the experimental app-server handshake and image turn", () => {
  assert.deepEqual(buildCodexInitialize().params.capabilities, { experimentalApi: true });
  assert.deepEqual(buildCodexThreadStart("least-cost-model"), {
    method: "thread/start", id: 1, params: { model: "least-cost-model" },
  });
  assert.equal(buildCodexThreadStart("openai-codex/gpt-5.6-luna").params.model, "gpt-5.6-luna");
  assert.deepEqual(buildCodexArtTurn("thread-1", "a tiny blue square"), {
    method: "turn/start", id: 2,
    params: { threadId: "thread-1", input: [{ type: "text", text: "a tiny blue square" }] },
  });
});

test("parses the app-server imageGeneration notification and savedPath", () => {
  assert.deepEqual(parseCodexArtEvent(JSON.stringify({
    method: "item/completed",
    params: { item: { type: "imageGeneration", status: "completed", savedPath: "/tmp/art.png", result: "ok" } },
  })), { status: "completed", savedPath: "/tmp/art.png", result: "ok", failure: null });
  assert.equal(parseCodexArtEvent('{"params":{"item":{"type":"image_generation"}}}'), null);
});

test("parses the current app-server snake_case saved_path field", () => {
  assert.deepEqual(parseCodexArtEvent(JSON.stringify({
    method: "item/completed",
    params: { item: { type: "imageGeneration", status: "completed", saved_path: "/tmp/current-art.png", result: "ok" } },
  })), { status: "completed", savedPath: "/tmp/current-art.png", result: "ok", failure: null });
});

test("runs the adapter lifecycle against a JSONL app-server boundary", async () => {
  const script = `
    const readline = require("node:readline");
    const rl = readline.createInterface({ input: process.stdin });
    rl.on("line", line => {
      const m = JSON.parse(line);
      if (m.id === 0) process.stdout.write(JSON.stringify({ id: 0, result: {} }) + "\\n");
      if (m.id === 1) process.stdout.write(JSON.stringify({ id: 1, result: { thread: { id: "fake-thread" } } }) + "\\n");
      if (m.id === 2) {
        process.stdout.write(JSON.stringify({ method: "rawResponse/completed", params: { responseId: "resp-art", usage: { input: 12, output: 3 } } }) + "\\n");
        process.stdout.write(JSON.stringify({ params: { item: { type: "imageGeneration", status: "completed", saved_path: "/tmp/fake-art.png", result: "ok" } } }) + "\\n");
      }
    });`;
  const result = await runCodexArt({ command: process.execPath, commandArgs: ["-e", script], prompt: "a tiny blue square", model: "least-cost-model", cwd: process.cwd() });
  assert.equal(result.savedPath, "/tmp/fake-art.png");
  assert.equal(result.providerRequestId, "resp-art");
  assert.deepEqual(result.usage, { input: 12, output: 3 });
  assert.ok(result.callId);
});

test("production callback sends bounded adapter bytes only when art direction is approved", async () => {
  const { createProductionExecutor } = await import("../src/runner.ts");
  const dir = await mkdtemp(path.join(tmpdir(), "ebook-art-"));
  const fixture = path.join(dir, "fixture-art.png");
  await writeFile(fixture, Buffer.concat([Buffer.from("\x89PNG\r\n\x1a\n"), Buffer.from("fixture")]))
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, body: options.body && JSON.parse(options.body) });
    if (url.endsWith("/context")) return Response.json({ project_id: "p", run_id: "r", brief: { art_direction: "blue square" } });
    if (url.endsWith("/providers")) return Response.json([{ provider: "openai-codex", scope: "app", protocol: "pi-native", orchestration_model: "m" }]);
    return Response.json({});
  };
  try {
    await createProductionExecutor({ baseUrl: "http://api", token: "secret", workerId: "w", runProduction: async () => ({ text: "# book", callId: "c" }), runArt: async () => ({ savedPath: fixture, callId: "art-call", providerRequestId: "resp-art", usage: { input: 12, output: 3 } }) })({ job_id: "j", generation: 1 });
    assert.equal(calls.at(-1).body.art.mime_type, "image/png");
    assert.equal(calls.at(-1).body.art.call_id, "art-call");
    assert.deepEqual(calls.at(-1).body.art.usage, { input: 12, output: 3 });
    assert.equal(Buffer.from(calls.at(-1).body.art.content_base64, "base64").toString(), "\x89PNG\r\n\x1a\nfixture");
  } finally { globalThis.fetch = originalFetch; await rm(dir, { recursive: true, force: true }); }
});
