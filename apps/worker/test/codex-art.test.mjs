import assert from "node:assert/strict";
import { test } from "node:test";
import { buildCodexArtTurn, buildCodexInitialize, buildCodexThreadStart, parseCodexArtEvent, runCodexArt } from "../src/codex-art.ts";

test("builds the experimental app-server handshake and image turn", () => {
  assert.deepEqual(buildCodexInitialize().params.capabilities, { experimentalApi: true });
  assert.deepEqual(buildCodexThreadStart("least-cost-model"), {
    method: "thread/start", id: 1, params: { model: "least-cost-model" },
  });
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

test("runs the adapter lifecycle against a JSONL app-server boundary", async () => {
  const script = `
    const readline = require("node:readline");
    const rl = readline.createInterface({ input: process.stdin });
    rl.on("line", line => {
      const m = JSON.parse(line);
      if (m.id === 0) process.stdout.write(JSON.stringify({ id: 0, result: {} }) + "\\n");
      if (m.id === 1) process.stdout.write(JSON.stringify({ id: 1, result: { thread: { id: "fake-thread" } } }) + "\\n");
      if (m.id === 2) process.stdout.write(JSON.stringify({ params: { item: { type: "imageGeneration", status: "completed", savedPath: "/tmp/fake-art.png", result: "ok" } } }) + "\\n");
    });`;
  const result = await runCodexArt({ command: process.execPath, commandArgs: ["-e", script], prompt: "a tiny blue square", model: "least-cost-model", cwd: process.cwd() });
  assert.equal(result.savedPath, "/tmp/fake-art.png");
});
