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

test("review leases use low-thinking Pi and fenced task-result accounting", async () => {
  const { createProductionExecutor } = await import("../src/runner.ts");
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (url.endsWith("/context")) return new Response(JSON.stringify({
      task_type: "review", project_id: "p", run_id: "r", task_id: "t", job_id: "j", brief: {}, budget: {},
      review_sections: [{ section_id: "s1", revision_id: "rev1", heading: "Opening", content: "Persisted prose." }],
    }), { status: 200 });
    if (url.endsWith("/providers")) return new Response(JSON.stringify([{ provider: "openai-codex", scope: "app", protocol: "pi-native", review_model: "gpt-5.6-luna" }]), { status: 200 });
    if (url.endsWith("/task-result")) return new Response(JSON.stringify({ accepted: true }), { status: 200 });
    throw new Error(`unexpected ${url}`);
  };
  try {
    await createProductionExecutor({
      baseUrl: "http://api", token: "secret", workerId: "w",
      runProduction: async (options) => {
        calls.push(options);
        assert.equal(options.thinking, "low");
        assert.equal(options.context.review_sections[0].revision_id, "rev1");
        return { text: "PASS: review complete", callId: "review-call", provider: "openai-codex", model: "gpt-5.6-luna", usage: { input_tokens: 8, output_tokens: 9 } };
      },
    })({ job_id: "j", generation: 1 });
  } finally {
    globalThis.fetch = originalFetch;
  }
  const taskResult = calls.find((entry) => entry?.url?.endsWith("/task-result"));
  assert.ok(taskResult);
  const body = JSON.parse(taskResult.options.body);
  assert.equal(body.result, "PASS: review complete");
  assert.equal(body.call_id, "review-call");
  assert.equal(body.provider, "openai-codex");
  assert.equal(body.model, "gpt-5.6-luna");
});

test("task roles choose their preferred configured models before fallbacks", async () => {
  const { createProductionExecutor } = await import("../src/runner.ts");
  const originalFetch = globalThis.fetch;
  const observed = [];
  globalThis.fetch = async (url) => {
    if (url.endsWith("/context")) return new Response(JSON.stringify({ task_type: globalThis.__taskType, project_id: "p", run_id: "r", task_id: "t", job_id: "j", brief: {}, budget: {} }), { status: 200 });
    if (url.endsWith("/providers")) return new Response(JSON.stringify([{ provider: "openai-codex", scope: "app", protocol: "pi-native", orchestration_model: "orchestrator", drafting_model: "drafter", review_model: "reviewer" }]), { status: 200 });
    return new Response(JSON.stringify({ accepted: true }), { status: 200 });
  };
  try {
    for (const taskType of ["outline", "production", "review"]) {
      globalThis.__taskType = taskType;
      await createProductionExecutor({ baseUrl: "http://api", token: "secret", workerId: "w", runProduction: async ({ model }) => { observed.push(model); return { text: "ok", callId: `${taskType}-call` }; } })({ job_id: "j", generation: 1 });
    }
  } finally {
    delete globalThis.__taskType;
    globalThis.fetch = originalFetch;
  }
  assert.deepEqual(observed, ["orchestrator", "drafter", "reviewer"]);
});
