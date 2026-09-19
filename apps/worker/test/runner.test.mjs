import assert from "node:assert/strict";
import test from "node:test";

test("outline leases use low-thinking Pi and fenced task-result callback", async () => {
  const { createProductionExecutor } = await import("../src/runner.ts");
  const calls = [];
  const runProduction = async (options) => {
    calls.push(options);
    return { text: "## Opening\nA bounded outline.", callId: "outline-call", usage: { input_tokens: 5, output_tokens: 7 } };
  };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (url.endsWith("/context")) {
      return new Response(JSON.stringify({ task_type: "outline", project_id: "p", run_id: "r", task_id: "t", job_id: "j", brief: {}, budget: {} }), { status: 200 });
    }
    if (url.endsWith("/providers")) return new Response(JSON.stringify([{ provider: "openai-codex", scope: "app", protocol: "pi-native", orchestration_model: "gpt-5.6-luna" }]), { status: 200 });
    if (url.endsWith("/task-result")) return new Response(JSON.stringify({ accepted: true }), { status: 200 });
    throw new Error(`unexpected ${url}`);
  };
  try {
    await createProductionExecutor({ baseUrl: "http://api", token: "secret", workerId: "w", runProduction })({ job_id: "j", generation: 1 });
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(calls.find((entry) => entry?.thinking !== undefined)?.thinking, "low");
  const taskResult = calls.find((entry) => entry?.url?.endsWith("/task-result"));
  assert.ok(taskResult);
  assert.equal(JSON.parse(taskResult.options.body).result, "## Opening\nA bounded outline.");
});

test("production leases pass bounded outline context and retain production result route", async () => {
  const { createProductionExecutor } = await import("../src/runner.ts");
  const requests = [];
  let received;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    requests.push(url);
    if (url.endsWith("/context")) return new Response(JSON.stringify({ task_type: "production", project_id: "p", run_id: "r", task_id: "t", job_id: "j", brief: {}, outline: { result: "outline" }, budget: {} }), { status: 200 });
    if (url.endsWith("/providers")) return new Response(JSON.stringify([{ provider: "openai-codex", scope: "app", protocol: "pi-native", orchestration_model: "gpt-5.6-luna" }]), { status: 200 });
    if (url.endsWith("/production-result")) { received = JSON.parse(options.body); return new Response(JSON.stringify({}), { status: 200 }); }
    throw new Error(`unexpected ${url}`);
  };
  try {
    await createProductionExecutor({ baseUrl: "http://api", token: "secret", workerId: "w", runProduction: async ({ context }) => { assert.equal(context.outline.result, "outline"); return { text: "# book", callId: "production-call" }; }, runArt: async () => null })({ job_id: "j", generation: 1 });
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.ok(requests.some((url) => url.endsWith("/production-result")));
  assert.equal(received.content, "# book");
});
