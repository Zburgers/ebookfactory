import assert from "node:assert/strict";
import test from "node:test";
import { createOrchestratorExecutor, runOrchestratorWorker } from "../src/orchestrator.ts";

test("trusted orchestrator executor passes its explicit skill path and safe system prompt", async () => {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (url.endsWith("/private/orchestrator/turn-3/context")) return new Response(JSON.stringify({ project_id: "p", messages: [] }), { status: 200 });
    if (url.endsWith("/private/worker/providers")) return new Response(JSON.stringify([{ provider: "openai-codex", scope: "app", protocol: "pi-native", orchestration_model: "gpt-5.6-luna" }]), { status: 200 });
    if (url.endsWith("/private/orchestrator/result")) return new Response(JSON.stringify({ state: "completed" }), { status: 200 });
    throw new Error(`unexpected request: ${url}`);
  };
  let observed;
  const execute = createOrchestratorExecutor({
    baseUrl: "http://api",
    token: "token",
    workerId: "worker-3",
    skillPaths: ["/trusted/kdp-publish"],
    runProduction: async (options) => {
      observed = options;
      return { text: "done", callId: "call-3", provider: "openai-codex", model: "gpt-5.6-luna", usage: null };
    },
  });

  await execute({ turn_id: "turn-3", generation: 1 });

  assert.deepEqual(observed.skillPaths, ["/trusted/kdp-publish"]);
  assert.match(observed.systemPrompt, /never publish|never.*KDP/i);
  assert.equal(calls.some((call) => call.url.endsWith("/private/orchestrator/result")), true);
});

test("reports execution failure to the fenced durable failure endpoint", async () => {
  const controller = new AbortController();
  const calls = [];
  const lease = { turn_id: "turn-1", worker_id: "worker-1", generation: 1, lease_until: new Date(Date.now() + 60000).toISOString() };
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (url.endsWith("/private/orchestrator/claim")) {
      if (calls.filter((call) => call.url.endsWith("/private/orchestrator/claim")).length === 1) return new Response(JSON.stringify(lease), { status: 200 });
      controller.abort();
      return new Response("null", { status: 200 });
    }
    if (url.endsWith("/private/orchestrator/turn-1/context")) return new Response(JSON.stringify({ messages: [] }), { status: 200 });
    if (url.endsWith("/private/worker/providers")) return new Response(JSON.stringify([{ provider: "openai-codex", scope: "app", protocol: "pi-native", orchestration_model: "gpt-5.6-luna" }]), { status: 200 });
    if (url.endsWith("/private/orchestrator/failure")) return new Response(JSON.stringify({ state: "queued" }), { status: 200 });
    throw new Error("unexpected request");
  };
  await runOrchestratorWorker({
    baseUrl: "http://api",
    token: "token",
    workerId: "worker-1",
    pollMs: 0,
    signal: controller.signal,
    runProduction: async () => { throw new Error("provider unavailable"); },
  });
  const failure = calls.find((call) => call.url.endsWith("/private/orchestrator/failure"));
  assert.ok(failure);
  assert.match(JSON.parse(failure.options.body).error, /provider unavailable/);
});

test("does not report a failure when the parent cancels the turn", async () => {
  const controller = new AbortController();
  const calls = [];
  const lease = { turn_id: "turn-2", worker_id: "worker-2", generation: 1, lease_until: new Date(Date.now() + 60000).toISOString() };
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (url.endsWith("/private/orchestrator/claim")) return new Response(JSON.stringify(lease), { status: 200 });
    if (url.endsWith("/private/orchestrator/turn-2/context")) return new Response(JSON.stringify({ messages: [] }), { status: 200 });
    if (url.endsWith("/private/worker/providers")) return new Response(JSON.stringify([{ provider: "openai-codex", scope: "app", protocol: "pi-native", orchestration_model: "gpt-5.6-luna" }]), { status: 200 });
    throw new Error("unexpected request");
  };
  await runOrchestratorWorker({
    baseUrl: "http://api",
    token: "token",
    workerId: "worker-2",
    signal: controller.signal,
    runProduction: async () => {
      controller.abort();
      throw new Error("shutdown");
    },
  });
  assert.equal(calls.some((call) => call.url.endsWith("/private/orchestrator/failure")), false);
});
